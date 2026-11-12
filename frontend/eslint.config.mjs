import js from '@eslint/js';
import ts from 'typescript-eslint';
export default ts.config(
  {ignores:['.next/**','node_modules/**','test-results/**','playwright-report/**','next-env.d.ts']},
  js.configs.recommended,
  ...ts.configs.recommended,
  {files:['scripts/*.mjs'],languageOptions:{globals:{process:'readonly'}}},
  {rules:{'@typescript-eslint/no-explicit-any':'off','@typescript-eslint/no-unused-vars':['error',{argsIgnorePattern:'^_',varsIgnorePattern:'^_'}]}}
);
