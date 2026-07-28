import { describe, expect, it } from "vitest"
import { buildTrainingConfig, checkTrainingConfig, hydrateImportedConfig } from "./params"

describe("training parameter conversion", () => {
  it("fills basic defaults and normalizes paths and GPU ids", () => {
    const result = buildTrainingConfig({
      pretrained_model_name_or_path: "D:\\models\\base.safetensors",
      train_data_dir: "D:\\train",
      gpu_ids: ["GPU 1: RTX", 2],
    }, "lora-basic")
    expect(result).toMatchObject({
      model_train_type: "sd-lora",
      network_module: "networks.lora",
      pretrained_model_name_or_path: "D:/models/base.safetensors",
      train_data_dir: "D:/train",
      gpu_ids: ["1", "2"],
    })
  })

  it("converts LyCORIS fields and custom arguments", () => {
    const result = buildTrainingConfig({
      model_train_type: "sdxl-lora",
      network_module: "lycoris.kohya",
      lycoris_algo: "lokr",
      conv_dim: 4,
      conv_alpha: 1,
      dropout: 0,
      lokr_factor: 8,
      train_norm: true,
      network_args_custom: ["custom=1"],
    }, "lora-master")
    expect(result.network_args).toEqual(["conv_dim=4", "conv_alpha=1", "dropout=0", "algo=lokr", "factor=8", "train_norm=True", "custom=1"])
    expect(result).not.toHaveProperty("lycoris_algo")
  })

  it("detects conflicting training options", () => {
    expect(checkTrainingConfig({ cache_latents: true, color_aug: true }).errors).toContain("参数 cache_latents 与 color_aug 冲突，请只启用其中一个")
  })

  it("hydrates canonical argument lists for the GUI", () => {
    expect(hydrateImportedConfig({ network_args: ["algo=loha", "factor=4"], optimizer_args: ["weight_decay=0.1"] })).toMatchObject({
      lycoris_algo: "loha",
      factor: "4",
      optimizer_args_custom: ["weight_decay=0.1"],
    })
  })
})
