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
  })
})
