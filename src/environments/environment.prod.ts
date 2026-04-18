// src/environments/environment.prod.ts
// Valores substituídos pelo CI via sed antes do ng build.
// Em local: copie environment.example.ts → environment.ts para desenvolvimento.
export const environment = {
  production:   true,
  apiUrl:       'https://laudifier-production-backend.whitehill-653d23c7.eastus2.azurecontainerapps.io',
  supabaseUrl:  'https://egxitnbmidyrwuteshfx.supabase.co',
  supabaseKey:  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVneGl0bmJtaWR5cnd1dGVzaGZ4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYzMDk5MzMsImV4cCI6MjA5MTg4NTkzM30.1QARBROBtObDanDs9zZGqDZHbR4pA2iwxD_2YypGVos',
  appName:      'Laudifier',
  appVersion:   '1.0.0',
};
