#!/bin/bash
#SBATCH -p standard96s:test
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --mail-user=j.rieling@stud.uni-goettingen.de
#SBATCH --mail-type=all
#SBATCH --output=slurm-out/%j.out

date
hostname
pwd

source /user/j.rieling/u12762/.bashrc

conda activate provenance-explorer
cd $SLURM_SUBMIT_DIR
pwd

echo "======== python ========"
echo "CPUs available: $SLURM_CPUS_PER_TASK"

python -c "
from provenance_explorer.analysis.provenance_capture.correctness.data_model_types_plot import DataModelTypesPlot

plot = DataModelTypesPlot()
plot.invalidate(data_model='cdm20')
plot.run(data_model='cdm20')
print('Done - cache written.')
"

echo "========================"
echo "All done in sbatch."

date
