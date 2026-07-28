// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import DynamicSchemaForm from "./DynamicSchemaForm.vue"
import type { AdaptedSchema } from "../schema/adapter"
import Schema from "schemastery"

const schema: AdaptedSchema = {
  name: "test",
  hash: "test",
  schema: Schema.object({}),
  sections: [{
    id: "main",
    title: "基础参数",
    fields: [
      { key: "mode", type: "string", options: ["basic", "advanced"], conditions: [] },
      { key: "steps", type: "number", conditions: [{ key: "mode", value: "advanced" }] },
      { key: "secret", type: "string", hidden: true, conditions: [] },
    ],
  }],
}

describe("DynamicSchemaForm", () => {
  it("renders active visible fields and propagates updates", async () => {
    const wrapper = mount(DynamicSchemaForm, {
      props: { schema, modelValue: { mode: "basic" }, errors: {} },
      global: { stubs: { SchemaField: { props: ["field"], template: "<button @click=\"$emit('update:modelValue', 12)\">{{ field.key }}</button>" } } },
    })

    expect(wrapper.text()).toContain("mode")
    expect(wrapper.text()).not.toContain("steps")
    expect(wrapper.text()).not.toContain("secret")
    await wrapper.get("button").trigger("click")
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([{ mode: 12 }])
  })
})
