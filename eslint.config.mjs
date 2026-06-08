import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';

const config = [
  ...nextCoreWebVitals,
  {
    linterOptions: {
      reportUnusedDisableDirectives: 'off',
    },
  },
  {
    rules: {
      'react-hooks/config': 'off',
      'react-hooks/error-boundaries': 'off',
      'react-hooks/gating': 'off',
      'react-hooks/globals': 'off',
      'react-hooks/immutability': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/set-state-in-render': 'off',
      'react-hooks/static-components': 'off',
      'react-hooks/use-memo': 'off',
      'react/display-name': 'warn',
    },
  },
  {
    ignores: [
      '.next/**',
      '**/.venv/**',
      'build/**',
      'coverage/**',
      'data/**',
      'dist/**',
      'external_Claudable/**',
      'node_modules/**',
      'out/**',
      'tmp/**',
    ],
  },
];

export default config;
