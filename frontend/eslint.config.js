import eslint from "@eslint/js"
import prettier from "eslint-config-prettier"
import tseslint from "typescript-eslint"
import vue from "eslint-plugin-vue"
import globals from "globals"

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "src/components.d.ts", "src/auto-imports.d.ts"] },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs["flat/recommended"],
  prettier,
  {
    files: ["src/**/*.{ts,vue}", "vite.config.ts"],
    languageOptions: { globals: globals.browser, parserOptions: { parser: tseslint.parser, extraFileExtensions: [".vue"] } },
    rules: {
      "vue/html-self-closing": "off",
      "vue/max-attributes-per-line": "off",
      "vue/multi-word-component-names": "off",
      "vue/no-deprecated-filter": "off",
      "vue/singleline-html-element-content-newline": "off",
      "no-empty": ["error", { "allowEmptyCatch": true }],
      "prefer-const": "off",
      "no-useless-assignment": "off",
    },
  },
)
