import heapq
import logging
import torch
import random
import json
import os
import time
import numpy as np
from pathlib import Path
from dptb.nnops.tester_dptb import DPTBTester
from dptb.nnops.tester_nnsk import NNSKTester
from typing import Dict, List, Optional, Any
from dptb.utils.loggers import set_log_handles
from dptb.utils.tools import j_loader, setup_seed
from dptb.utils.constants import dtype_dict
from dptb.plugins.init_nnsk import InitSKModel
from dptb.plugins.init_dptb import InitDPTBModel
from dptb.plugins.init_data import InitTestData
from dptb.utils.argcheck import normalize
from dptb.plugins.monitor import TestLossMonitor
from dptb.plugins.train_logger import Logger

__all__ = ["validation"]

log = logging.getLogger(__name__)

def validation(
        INPUT: str,
        init_model: str,
        output: str,
        log_level: int,
        log_path: Optional[str],
        test_sk: bool,
        use_correction: Optional[str],
        **kwargs
):
    run_opt = {
        "init_model": init_model,
        "log_path": log_path,
        "log_level": log_level,
        "test_sk": test_sk,
        "use_correction": use_correction,
        "freeze":True
    }
    
    if all((use_correction, test_sk)):
        log.error(msg="--use-correction and --train_sk should not be set at the same time")
        raise RuntimeError
    
    # setup INPUT path
    if test_sk:
        if init_model:
            skconfig_path = os.path.join(str(Path(init_model).parent.absolute()), "config_nnsktb.json")
            mode = "init_model"
        else:
            log.error("ValueError: Missing init_model file path.")
            raise ValueError
    else:
        if init_model:
            dptbconfig_path = os.path.join(str(Path(init_model).parent.absolute()), "config_dptbtb.json")
            mode = "init_model"
        else:
            log.error("ValueError: Missing init_model file path.")
            raise ValueError

        if use_correction:
            skconfig_path = os.path.join(str(Path(use_correction).parent.absolute()), "config_nnsktb.json")
        else:
            skconfig_path = None
    
    # setup output path
    if output:
        Path(output).parent.mkdir(exist_ok=True, parents=True)
        Path(output).mkdir(exist_ok=True, parents=True)
        results_path = os.path.join(str(output), "results")
        Path(results_path).mkdir(exist_ok=True, parents=True)
        if not log_path:
            log_path = os.path.join(str(output), "log/log.txt")
        Path(log_path).parent.mkdir(exist_ok=True, parents=True)

        run_opt.update({
                        "output": str(Path(output).absolute()),
                        "results_path": str(Path(results_path).absolute()),
                        "log_path": str(Path(log_path).absolute())
                        })
    run_opt.update({"mode": mode})
    if test_sk:
        run_opt.update({
            "skconfig_path": skconfig_path,
        })
    else:
        if use_correction:
            run_opt.update({
                "skconfig_path": skconfig_path
            })
        run_opt.update({
            "dptbconfig_path": dptbconfig_path
        })
    set_log_handles(log_level, Path(log_path) if log_path else None)

    jdata = j_loader(INPUT)
    jdata = normalize(jdata)
    setup_seed(seed=jdata["train_options"]["seed"])


    with open(os.path.join(output, "test_config.json"), "w") as fp:
            json.dump(jdata, fp, indent=4)
    

    str_dtype = jdata["common_options"]["dtype"]
    jdata["common_options"]["dtype"] = dtype_dict[jdata["common_options"]["dtype"]]
    

    if test_sk:
        tester = NNSKTester(run_opt, jdata)
        tester.register_plugin(InitSKModel())
    else:
        tester = DPTBTester(run_opt, jdata)
        tester.register_plugin(InitDPTBModel())
    
    # register the plugin in tester, to tract training info
    tester.register_plugin(InitTestData())
    tester.register_plugin(TestLossMonitor())
    tester.register_plugin(Logger(["test_loss"], 
        interval=[(jdata["train_options"]["display_freq"], 'iteration'), (1, 'epoch')]))
    
    for q in tester.plugin_queues.values():
        heapq.heapify(q)
    
    tester.build()

    if output:
        # output training configurations:
        with open(os.path.join(output, "test_config.json"), "w") as fp:
            jdata["common_options"]["dtype"] = str_dtype
            json.dump(jdata, fp, indent=4)

        #tester.register_plugin(Saver(
            #interval=[(jdata["train_options"].get("save_freq"), 'epoch'), (1, 'iteration')] if jdata["train_options"].get(
            #    "save_freq") else None))
        #    interval=[(jdata["train_options"].get("save_freq"), 'iteration'),  (1, 'epoch')] if jdata["train_options"].get(
        #        "save_freq") else None))
        # add a plugin to save the training parameters of the model, with model_output as given path

    start_time = time.time()

    tester.run(epochs=1)

    end_time = time.time()
    log.info("finished testing")