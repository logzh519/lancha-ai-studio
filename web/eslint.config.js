/** 前端边界约束（对应后端 tests/platforms/test_architecture.py）：
 *   shell  -> 只能引用 shared 和自己
 *   shared -> 只能引用自己
 *   module -> 只能引用 shared 和同名模块，模块之间一律不互相引用
 * 需要共用的东西，提到 shared 里。
 */

import js from '@eslint/js'
import boundaries from 'eslint-plugin-boundaries'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  // essential 只管正确性；排版交给编辑器和 prettier，不在 lint 里制造噪音
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    files: ['src/shell/App.vue'],
    rules: { 'vue/multi-word-component-names': 'off' },
  },
  {
    files: ['src/**/*.{ts,vue}'],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { boundaries },
    settings: {
      // 没有 resolver 时 boundaries 会把所有相对路径判成 unknown 并静默放过，规则形同虚设
      'import/resolver': { typescript: { project: './tsconfig.json' } },
      'boundaries/include': ['src/**/*'],
      'boundaries/elements': [
        { type: 'main', pattern: 'src/main.ts', mode: 'file' },
        { type: 'shell', pattern: 'src/shell/**', mode: 'full' },
        { type: 'shared', pattern: 'src/shared/**', mode: 'full' },
        { type: 'module', pattern: 'src/modules/*/**', mode: 'full', capture: ['name'] },
      ],
    },
    rules: {
      'boundaries/element-types': [
        'error',
        {
          default: 'disallow',
          rules: [
            { from: 'main', allow: ['shell', 'shared'] },
            { from: 'shell', allow: ['shell', 'shared'] },
            { from: 'shared', allow: ['shared'] },
            { from: 'module', allow: ['shared', ['module', { name: '${from.name}' }]] },
          ],
        },
      ],
      // resolver 失效时会退化成 unknown，这条规则保证退化不会被悄悄忽略
      'boundaries/no-unknown': 'error',
    },
  },
)
