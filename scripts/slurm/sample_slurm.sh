#!/bin/bash
#SBATCH -p standard96s
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --mail-user=email@example.de
#SBATCH --mail-type=all
#SBATCH --output=slurm-out/sample_script_%j.out

date
hostname
pwd

source /user/your_account/your_user/.bashrc 

conda activate provenance-explorer
cd $SLURM_SUBMIT_DIR
pwd

echo "======== python ========"
echo "CPUs available: $SLURM_CPUS_PER_TASK"

python -c "
from provenance_explorer.analysis.provenance_capture.correctness.data_model_types_plot import DataModelTypesPlot

plot = DataModelTypesPlot()
plot.invalidate(data_model='ecar')
plot.run(data_model='ecar')
print('Done - cache written.')
"

echo "========================"
echo "All done in sbatch."

date
