"""
Goes through test period of optc iterator and saved the first three occurences of
certain object+action pairs.
"""
from provenance_explorer.registry.darpa_optc_registry import OPTC_ALL
from provenance_explorer.registry.registry_all import REPO_ROOT
from provenance_explorer.raw_file_handling.parsing_helpers import PARSERS, TS_EXTRACTORS
from provenance_explorer.raw_file_handling.dataset_iterator import make_dataset_iterator

from collections import defaultdict
from pathlib import Path
from pprint import pformat

if __name__ == "__main__":

    for sub_dataset, registry in OPTC_ALL.items():
        ts_extr = TS_EXTRACTORS[("optc", sub_dataset)]
        parse_fn = PARSERS[("optc", sub_dataset)]

        iterator = make_dataset_iterator(
            registry=registry,
            parse_fn=parse_fn,
            ts_extractor=ts_extr,
            test_run_seconds=30,
        )
        
        counters = defaultdict(int)
        samples = defaultdict(list)

        for ts, rec in iterator: 
            obj = rec["object"]
            action = rec["action"]

            key = (obj, action)
            counters[key] += 1

            if counters[key] > 3:
                continue
            else:
                samples[key].append(rec)

        out_dir = Path(REPO_ROOT) / "data_samples" / "optc" / sub_dataset
        out_dir.mkdir(parents=True, exist_ok=True)

        out_file = out_dir / "object_action_samples.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(pformat(dict(samples), sort_dicts=False))