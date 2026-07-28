<script setup lang="ts">
import { computed } from "vue"
import type { AdaptedSchema, FormField, FormModel } from "../schema/adapter"
import { isFieldActive } from "../schema/adapter"
import SchemaField from "./SchemaField.vue"

const props = defineProps<{ schema: AdaptedSchema; modelValue: FormModel; errors: Record<string, string> }>()
const emit = defineEmits<{ "update:modelValue": [value: FormModel] }>()

const selectedFields = computed(() => {
  const result = new Map<string, FormField>()
  for (const section of props.schema.sections) {
    for (const field of section.fields) {
      if (isFieldActive(field, props.modelValue)) result.set(field.key, field)
    }
  }
  return result
})

function visibleFields(fields: FormField[]) {
  return fields.filter((field) => !field.hidden && selectedFields.value.get(field.key) === field)
}

function update(key: string, value: FormModel[string]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value })
}
</script>

<template>
  <div class="schema-form">
    <section v-for="section in schema.sections" v-show="visibleFields(section.fields).length" :key="section.id" class="schema-section">
      <header><h2>{{ section.title }}</h2><span>{{ visibleFields(section.fields).length }} 项</span></header>
      <div class="schema-fields">
        <SchemaField v-for="field in visibleFields(section.fields)" :key="field.key" :field="field" :model-value="modelValue[field.key]" :error="errors[field.key]" @update:model-value="update(field.key, $event)" />
      </div>
    </section>
  </div>
</template>
