import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { createDefaultModel, executeSchemaSources, serializeModel } from "./adapter"

const sources = [
  {
    name: "shared",
    hash: "shared",
    schema: "(() => ({ COMMON: Schema.object({ output_name: Schema.string().default('model') }).description('保存设置') }))()",
  },
  {
    name: "training",
    hash: "training",
    schema: `Schema.intersect([
      Schema.object({
        enabled: Schema.boolean().default(false),
        mode: Schema.union(['a', 'b']).default('a'),
        hidden_value: Schema.const('fixed').default('fixed').hidden(),
      }).description('基础设置'),
      SHARED_SCHEMAS.COMMON,
      Schema.union([
        Schema.object({ enabled: Schema.const(true).required(), detail: Schema.number().min(1).default(2) }),
        Schema.object({}),
      ]),
    ])`,
  },
]

describe("dynamic schema adapter", () => {
  it("executes shared schemas and creates defaults", () => {
    const schema = executeSchemaSources(sources, "training")
    expect(createDefaultModel(schema)).toMatchObject({ enabled: false, mode: "a", hidden_value: "fixed", output_name: "model", detail: 2 })
  })

  it("serializes only fields from the active conditional branch", () => {
    const schema = executeSchemaSources(sources, "training")
    const model = createDefaultModel(schema)
    expect(serializeModel(schema, model)).not.toHaveProperty("detail")
    model.enabled = true
    expect(serializeModel(schema, model)).toMatchObject({ enabled: true, detail: 2 })
  })

  it("does not replace a controlling field with its conditional const", () => {
    const schema = executeSchemaSources(sources, "training")
    const enabledFields = schema.sections.flatMap((section) => section.fields).filter((field) => field.key === "enabled")
    expect(enabledFields).toHaveLength(1)
    expect(enabledFields[0].type).toBe("boolean")
  })

  it("treats non-required const fields as union discriminators", () => {
    const conditionalSources = [{
      name: "conditional",
      hash: "conditional",
      schema: `Schema.intersect([
        Schema.object({ mode: Schema.union(['sd-lora', 'sdxl-lora']).default('sdxl-lora') }),
        Schema.union([
          Schema.object({ mode: Schema.const('sd-lora'), v2: Schema.boolean().default(false) }),
          Schema.object({}),
        ]),
      ])`,
    }]
    const schema = executeSchemaSources(conditionalSources, "conditional")
    const modeFields = schema.sections.flatMap((section) => section.fields).filter((field) => field.key === "mode")
    expect(modeFields).toHaveLength(1)
    expect(modeFields[0].options).toEqual(["sd-lora", "sdxl-lora"])
  })

  it("serializes hidden const fields instead of treating them as discriminators", () => {
    const conditionalSources = [{
      name: "conditional",
      hash: "conditional",
      schema: `Schema.intersect([
        Schema.object({ mode: Schema.union(['a', 'b']).default('a') }),
        Schema.union([
          Schema.object({
            mode: Schema.const('a'),
            implementation: Schema.const('module.a').default('module.a').hidden(),
          }),
          Schema.object({
            mode: Schema.const('b'),
            implementation: Schema.const('module.b').default('module.b').hidden(),
          }),
        ]),
      ])`,
    }]
    const schema = executeSchemaSources(conditionalSources, "conditional")
    const model = createDefaultModel(schema)

    expect(serializeModel(schema, model)).toMatchObject({ mode: "a", implementation: "module.a" })
    model.mode = "b"
    expect(serializeModel(schema, model)).toMatchObject({ mode: "b", implementation: "module.b" })
  })

  it("executes every backend training schema", () => {
    const schemaDir = resolve(process.cwd(), "../mikazuki/schema")
    const realSources = readdirSync(schemaDir).filter((name) => name.endsWith(".ts")).map((file) => ({
      name: file.slice(0, -3),
      hash: file,
      schema: readFileSync(resolve(schemaDir, file), "utf8"),
    }))
    for (const source of realSources.filter((item) => item.name !== "shared")) {
      const schema = executeSchemaSources(realSources, source.name)
      expect(schema.sections.length, source.name).toBeGreaterThan(0)
      expect(Object.keys(createDefaultModel(schema)).length, source.name).toBeGreaterThan(0)
    }

    const master = executeSchemaSources(realSources, "lora-master")
    const trainTypeFields = master.sections.flatMap((section) => section.fields).filter((field) => field.key === "model_train_type")
    expect(trainTypeFields).toHaveLength(1)
    expect(trainTypeFields[0].options).toEqual(["sd-lora", "sdxl-lora"])
    expect(serializeModel(master, createDefaultModel(master))).toMatchObject({
      model_train_type: "sdxl-lora",
      network_module: "networks.lora",
    })

    const flux = executeSchemaSources(realSources, "flux-lora")
    expect(serializeModel(flux, createDefaultModel(flux))).toMatchObject({
      model_train_type: "flux-lora",
      model_type: "flux",
      network_module: "networks.lora_flux",
    })

    const anima = executeSchemaSources(realSources, "sd3-lora")
    const animaModel = createDefaultModel(anima)
    const expectedModules = {
      lora: "networks.lora_anima",
      lokr: "lycoris.kohya",
      tlora: "networks.tlora_anima",
      lora_fa: "networks.lora_anima",
      vera: "networks.lora_anima",
      loha: "networks.loha",
    }
    for (const [loraType, networkModule] of Object.entries(expectedModules)) {
      animaModel.lora_type = loraType
      expect(serializeModel(anima, animaModel).network_module, loraType).toBe(networkModule)
    }

    const animaFast = executeSchemaSources(realSources, "anima-lora-fast")
    expect(serializeModel(animaFast, createDefaultModel(animaFast))).toMatchObject({
      lora_type: "lora",
      method: "lora",
      methods_subdir: "gui-methods",
      network_module: "networks.lora_anima",
    })
  })
})
