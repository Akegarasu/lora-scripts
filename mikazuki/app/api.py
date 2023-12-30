import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import toml
from fastapi import APIRouter, BackgroundTasks, Request
from starlette.requests import Request

import mikazuki.process as process
from mikazuki import launch_utils
from mikazuki.app.models import TaggerInterrogateRequest
from mikazuki.log import log
from mikazuki.tagger.interrogator import (available_interrogators,
                                          on_interrogate)
from mikazuki.tasks import tm
from mikazuki.utils import train_utils
from mikazuki.utils.devices import printable_devices
from mikazuki.utils.tk_window import (open_directory_selector,
                                      open_file_selector)

router = APIRouter()

avaliable_scripts = [
    "networks/extract_lora_from_models.py",
    "networks/extract_lora_from_dylora.py"
]

trainer_mapping = {
    "sd-lora": "./sd-scripts/train_network.py",
    "sdxl-lora": "./sd-scripts/sdxl_train_network.py",
    "sd-dreambooth": "./sd-scripts/train_db.py",
    "sdxl-finetune": "./sd-scripts/sdxl_train.py",
}


@router.post("/run")
async def create_toml_file(request: Request):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    toml_file = os.path.join(os.getcwd(), f"config", "autosave", f"{timestamp}.toml")
    json_data = await request.body()
    config = json.loads(json_data.decode("utf-8"))

    gpu_ids = config.pop("gpu_ids", ["0"])
    suggest_cpu_threads = 8 if len(train_utils.get_total_images(config["train_data_dir"])) > 200 else 2
    model_train_type = config.pop("model_train_type", "sd-lora")
    trainer_file = trainer_mapping[model_train_type]

    if model_train_type != "sdxl-finetune":
        if not train_utils.validate_data_dir(config["train_data_dir"]):
            return {
                "status": "fail",
                "detail": "训练数据集路径不存在或没有图片，请检查目录。"
            }

    validated, message = train_utils.validate_model(config["pretrained_model_name_or_path"])
    if not validated:
        return {
            "status": "fail",
            "detail": message
        }

    sample_prompts = config.get("sample_prompts", None)
    if sample_prompts is not None and not os.path.exists(sample_prompts) and train_utils.is_promopt_like(sample_prompts):
        sample_prompts_file = os.path.join(os.getcwd(), f"config", "autosave", f"{timestamp}-promopt.txt")
        with open(sample_prompts_file, "w", encoding="utf-8") as f:
            f.write(sample_prompts)
        config["sample_prompts"] = sample_prompts_file
        log.info(f"Wrote promopts to file {sample_prompts_file}")

    with open(toml_file, "w") as f:
        f.write(toml.dumps(config))

    coro = asyncio.to_thread(process.run_train, toml_file, trainer_file, gpu_ids, suggest_cpu_threads)
    asyncio.create_task(coro)

    return {"status": "success"}


@router.post("/run_script")
async def run_script(request: Request, background_tasks: BackgroundTasks):
    paras = await request.body()
    j = json.loads(paras.decode("utf-8"))
    script_name = j["script_name"]
    if script_name not in avaliable_scripts:
        return {"status": "fail"}
    del j["script_name"]
    result = []
    for k, v in j.items():
        result.append(f"--{k}")
        if not isinstance(v, bool):
            value = str(v)
            if " " in value:
                value = f'"{v}"'
            result.append(value)
    script_args = " ".join(result)
    script_path = Path(os.getcwd()) / "sd-scripts" / script_name
    cmd = f"{launch_utils.python_bin} {script_path} {script_args}"
    background_tasks.add_task(launch_utils.run, cmd)
    return {"status": "success"}


@router.post("/interrogate")
async def run_interrogate(req: TaggerInterrogateRequest, background_tasks: BackgroundTasks):
    interrogator = available_interrogators.get(req.interrogator_model, available_interrogators["wd14-convnextv2-v2"])
    background_tasks.add_task(
        on_interrogate,
        image=None,
        batch_input_glob=req.path,
        batch_input_recursive=req.batch_input_recursive,
        batch_output_dir="",
        batch_output_filename_format="[name].[output_extension]",
        batch_output_action_on_conflict=req.batch_output_action_on_conflict,
        batch_remove_duplicated_tag=True,
        batch_output_save_json=False,
        interrogator=interrogator,
        threshold=req.threshold,
        additional_tags=req.additional_tags,
        exclude_tags=req.exclude_tags,
        sort_by_alphabetical_order=False,
        add_confident_as_weight=False,
        replace_underscore=req.replace_underscore,
        replace_underscore_excludes=req.replace_underscore_excludes,
        escape_tag=req.escape_tag,
        unload_model_after_running=True
    )
    return {"status": "success"}

# @router.get("/api/schema/{name}")
# async def get_schema(name: str):
#     with open(os.path.join(os.getcwd(), "mikazuki", "schema", name), encoding="utf-8") as f:
#         content = f.read()
#         return Response(content=content, media_type="text/plain")


@router.get("/pick_file")
async def pick_file(picker_type: str):
    if picker_type == "folder":
        coro = asyncio.to_thread(open_directory_selector, os.getcwd())
    elif picker_type == "modelfile":
        file_types = [("checkpoints", "*.safetensors;*.ckpt;*.pt"), ("all files", "*.*")]
        coro = asyncio.to_thread(open_file_selector, os.getcwd(), "Select file", file_types)

    result = await coro
    if result == "":
        return {
            "status": "fail"
        }

    return {
        "status": "success",
        "path": result
    }


@router.get("/tasks")
async def get_tasks():
    return tm.dump()


@router.get("/tasks/terminate/{task_id}")
async def terminate_task(task_id: str):
    tm.terminate_task(task_id)
    return {"status": "success"}


@router.get("/graphic_cards")
async def list_avaliable_cards():
    if not printable_devices:
        return {
            "status": "pending"
        }

    return {
        "status": "success",
        "cards": printable_devices
    }
