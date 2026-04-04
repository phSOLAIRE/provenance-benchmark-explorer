"""
mttkrp_helpers.py

Non-negative CP (PARAFAC) decomposition for sparse 3-way tensors.

Implements ALS approach to non-negative tensor factorization as described in:
    Gauvin et al. 2014, Detecting the Community Structure and Activity Patterns of Temporal Networks: A Non-Negative Tensor Factorization Approach.

The tensor T in R^{N x N x S} is approximated as a sum of R rank-1 components
T ~~ [[A, B, C]], where 
A (N x R) and B (N x R) encode community membership and
C (S x R) encodes temporal activity patterns.

Functions:
    - SparseTensor3         Slice-wise CSR representation of a 3-way tensor.
    - build_sparse_tensor   Construct a SparseTensor3 from (slice, row, col) event list.
    - mttkrp_mode0,1,2      Matricized-tensor times Khatri-Rao product for each mode (see paper).
    - sparse_nonneg_cp      Non-negative CP via ALS with multiplicative updates using the modes.
    - run_sweep             Sweep over a range of R values
    - select_R              select the best rank guided by core consistency

    - compute_core_consistency_sparse: Core consistency diagnostic for avoiding overfitting, 
            originally from (Bro & Kliers, 2003, A new efficient method for determining the number of components in PARAFAC models),
            values > 50% indicate a robust decomposition.
"""

import numpy as np
import time as time_module
from scipy.sparse import csr_matrix, lil_matrix
from typing import List, Tuple, Dict
import gc

from dataclasses import dataclass, field

@dataclass
class SparseTensor3:
    slices: List[csr_matrix]
    n_rows: int
    n_cols: int
    n_slices: int
    _norm_sq: float = None # type: ignore
    
    @property
    def nnz(self):
        return sum(s.nnz for s in self.slices)
    
    @property
    def norm_sq(self):
        if self._norm_sq is None:
            self._norm_sq = sum(s.multiply(s).sum() for s in self.slices) # type: ignore
        return self._norm_sq

def build_sparse_tensor(events, N, S):
    lils = [lil_matrix((N, N), dtype=np.float32) for _ in range(S)]
    for (b, s, d) in events:
        lils[b][s, d] += 1
    slices = [l.tocsr() for l in lils]
    del lils
    gc.collect()
    return SparseTensor3(slices=slices, n_rows=N, n_cols=N, n_slices=S) # type: ignore

def run_sweep(tensor, r_range, n_inits=5, max_iter=100, tol=1e-4, verbose=True):
    T_norm = np.sqrt(tensor.norm_sq)
    results = []
    
    for R in r_range:
        best_err, best_ABC = np.inf, None
        t0 = time_module.time()
        
        for init in range(n_inits):
            A, B, C, errs = sparse_nonneg_cp(
                tensor, R, max_iter=max_iter, tol=tol,
                seed=init*7+13, verbose=False)
            rel_err = errs[-1] / T_norm
            if rel_err < best_err:
                best_err = rel_err
                best_ABC = (A, B, C)
        
        elapsed = time_module.time() - t0
        
        A, B, C = best_ABC # type: ignore
        cc = compute_core_consistency_sparse(tensor, A, B, C)
        
        results.append({
            'R': R, 'rel_error': best_err,
            'core_consistency': cc, 'elapsed_s': elapsed,
            'factors': best_ABC,
        })
        
        if verbose:
            expl = (1 - best_err**2) * 100
            print(f'R={R:2d}  CC={cc:7.1f}%  err={best_err:.4f} expl={expl:.1f}%  {elapsed:.1f}s')
        gc.collect()
    
    return results

def select_R(results, cc_threshold=50.0):
    best = results[0]['R']
    for r in results:
        if r['core_consistency'] >= cc_threshold:
            best = r['R']
    return best

def mttkrp_mode0(tensor: SparseTensor3, B: np.ndarray, C: np.ndarray) -> np.ndarray:
    """result[i,r] = for updating A."""
    R = B.shape[1]
    result = np.zeros((tensor.n_rows, R), dtype=np.float64)
    for k in range(tensor.n_slices):
        Sk = tensor.slices[k]
        if Sk.nnz == 0:
            continue
        result += Sk.dot(B) * C[k, :][np.newaxis, :]
    return result

def mttkrp_mode1(tensor: SparseTensor3, A: np.ndarray, C: np.ndarray) -> np.ndarray:
    """result[j,r] for updating B."""
    R = A.shape[1]
    result = np.zeros((tensor.n_cols, R), dtype=np.float64)
    for k in range(tensor.n_slices):
        Sk = tensor.slices[k]
        if Sk.nnz == 0:
            continue
        result += Sk.T.dot(A) * C[k, :][np.newaxis, :]
    return result

def mttkrp_mode2(tensor: SparseTensor3, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """result[k,r] for updating C."""
    R = A.shape[1]
    result = np.zeros((tensor.n_slices, R), dtype=np.float64)
    for k in range(tensor.n_slices):
        Sk = tensor.slices[k]
        if Sk.nnz == 0:
            continue
        SB = Sk.dot(B)
        result[k, :] = np.sum(A * SB, axis=0)
    return result

def compute_core_consistency_sparse(tensor: SparseTensor3,A: np.ndarray, B: np.ndarray,C: np.ndarray) -> float:
    R = A.shape[1]
    Ap = np.linalg.pinv(A)
    Bp = np.linalg.pinv(B)
    Cp = np.linalg.pinv(C)

    G = np.zeros((R, R, R), dtype=np.float64)
    for k in range(tensor.n_slices):
        Sk = tensor.slices[k]
        if Sk.nnz == 0:
            continue
        # Ap @ Sk @ Bp.T  gives (R, R)
        mid = Ap @ Sk.toarray() @ Bp.T  # (R, R)
        for p in range(R):
            G[:, :, p] += mid * Cp[p, k]

    # Superdiagonal
    g1 = np.zeros((R, R, R))
    for r in range(R):
        g1[r, r, r] = 1.0

    return 100.0 * (1.0 - np.sum((G - g1)**2) / R)

def sparse_nonneg_cp(
    tensor: SparseTensor3, R: int,
    max_iter: int = 100, tol: float = 1e-4,
    seed: int = 42, verbose: bool = False
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[float]]:

    N = tensor.n_rows
    S = tensor.n_slices
    eps = 1e-12
    
    rng = np.random.default_rng(seed)
    A = np.abs(rng.standard_normal((N, R))) * 0.01
    B = np.abs(rng.standard_normal((N, R))) * 0.01
    C = np.abs(rng.standard_normal((S, R))) * 0.01
    
    T_norm_sq = tensor.norm_sq
    errors = []
    
    # ALS as mentioned in Gauvin 2015
    for it in range(max_iter):
        t0 = time_module.time()
        
        # Update A
        num_A = mttkrp_mode0(tensor, B, C)
        den_A = (B.T @ B) * (C.T @ C)  # R x R, elementwise Hadamard
        A = num_A @ np.linalg.pinv(den_A)
        A = np.maximum(A, eps)
        
        # Update B
        num_B = mttkrp_mode1(tensor, A, C)
        den_B = (A.T @ A) * (C.T @ C)
        B = num_B @ np.linalg.pinv(den_B)
        B = np.maximum(B, eps)
        
        # Update C
        num_C = mttkrp_mode2(tensor, A, B)
        den_C = (A.T @ A) * (B.T @ B)
        C = num_C @ np.linalg.pinv(den_C)
        C = np.maximum(C, eps)
        
        # Error via Gram trick
        inner = np.sum(num_C * C)
        gram = (A.T @ A) * (B.T @ B) * (C.T @ C)
        err = np.sqrt(max(T_norm_sq - 2*inner + np.sum(gram), 0))
        errors.append(err)
        
        elapsed = time_module.time() - t0
        if verbose and (it < 3 or it % 20 == 0 or it == max_iter-1):
            print(f'  it {it:3d}: err={err:.2f}  ({elapsed:.1f}s)')
        
        if it > 0:
            rel_change = abs(errors[-1] - errors[-2]) / (errors[-2] + eps)
            if rel_change < tol:
                if verbose:
                    print(f'Converged at it {it} (Δ={rel_change:.1e})')
                break
    
    return A, B, C, errors