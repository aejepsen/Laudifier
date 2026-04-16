// src/environments/environment.prod.ts
// Valores substituídos pelo CI via sed antes do ng build.
// Em local: copie environment.example.ts → environment.ts para desenvolvimento.
export const environment = {
  production:   true,
  apiUrl:       'REPLACE_API_URL',
  supabaseUrl:  'REPLACE_SUPABASE_URL',
  supabaseKey:  'REPLACE_SUPABASE_KEY',
  appName:      'Laudifier',
  appVersion:   '1.0.0',
};
