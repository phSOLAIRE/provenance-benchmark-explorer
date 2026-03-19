"""
Goes through test period of e5 iterator and saved the first three occurences of
certain types and subtypes.
"""
from provenance_explorer.registry.darpa_e5_registry import E5_ALL
from provenance_explorer.registry.registry_all import REPO_ROOT
from provenance_explorer.raw_file_handling.parsing_helpers import PARSERS, TS_EXTRACTORS
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator

from collections import defaultdict
from pathlib import Path
from pprint import pformat

if __name__ == "__main__":

    for sub_dataset, registry in E5_ALL.items():
        ts_extr = TS_EXTRACTORS[("e5", sub_dataset)] # needed for test function to work
        parse_fn = PARSERS[("e5", sub_dataset)]

        iterator = make_dataset_iterator(
            registry=registry,
            parse_fn=parse_fn,
            ts_extractor=ts_extr,
            test_run_seconds=5,
        )
        
        counters = defaultdict(int)
        samples = {}

        for ts, rec in iterator: 
            rec = rec["datum"]
            rec_type = next(iter(rec.keys()))

            counters[rec_type] += 1

            if counters[rec_type] > 3: 
                continue
            else: 
                samples.setdefault(rec_type, []).append(rec)

        out_dir = Path(REPO_ROOT)/ "data_samples" / "e5" / sub_dataset
        out_dir.mkdir(parents=True, exist_ok=True)

        out_file = out_dir / "type_samples.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(pformat(samples, sort_dicts=False))