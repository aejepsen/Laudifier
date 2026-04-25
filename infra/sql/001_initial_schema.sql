-- 001_initial_schema.sql
-- Schema inicial do Laudifier: tabelas laudos + user_profiles, com RLS.
-- Aplicar no Supabase Dashboard → SQL Editor.
-- Idempotente: pode rodar múltiplas vezes sem efeito colateral.

-- ── laudos ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.laudos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    especialidade  TEXT NOT NULL,
    tipo_laudo     TEXT,
    solicitacao    TEXT,
    laudo          TEXT NOT NULL,
    laudo_editado  TEXT,
    tipo_geracao   TEXT,                                 -- 'rag' | 'fallback'
    laudos_ref     JSONB DEFAULT '[]'::jsonb,
    aprovado       BOOLEAN,
    correcoes      TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.laudos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_own_laudos" ON public.laudos;
CREATE POLICY "users_own_laudos"
    ON public.laudos
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_laudos_especialidade
    ON public.laudos(especialidade);
CREATE INDEX IF NOT EXISTS idx_laudos_user_created
    ON public.laudos(user_id, created_at DESC);

-- ── user_profiles ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    display_name   TEXT,
    crm            TEXT,
    especialidade  TEXT,
    role           TEXT DEFAULT 'medico',               -- 'medico' | 'admin'
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_own_profile" ON public.user_profiles;
CREATE POLICY "users_own_profile"
    ON public.user_profiles
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Auto-criar profile vazio quando usuário se cadastra (se ainda não existir)
INSERT INTO public.user_profiles (user_id, display_name, role)
SELECT id, COALESCE(raw_user_meta_data->>'display_name', email), 'medico'
FROM auth.users
ON CONFLICT (user_id) DO NOTHING;
