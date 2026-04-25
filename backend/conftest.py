import os
import sys
from pathlib import Path

# Adiciona o diretório pai de backend/ ao path para que
# os imports `from backend.xxx` funcionem ao rodar pytest de dentro de backend/
# e `from api.xxx` funcionem ao rodar de fora.
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Env defaults dummy — APENAS para suite de testes.
# Garante que clients externos (Supabase, Anthropic, Qdrant, S3) consigam ser
# instanciados sem env real. Testes individuais devem mockar a camada de IO.
# `setdefault` preserva valores reais se já existirem (ex.: CI com secrets).
os.environ.setdefault("SUPABASE_URL", "http://stub.supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "stub-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "stub-anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "stub-jwt-secret-for-tests-only-32bytes")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-stub-test-key")
os.environ.setdefault("QDRANT_URL", "https://stub.qdrant.test:6333")
os.environ.setdefault("QDRANT_API_KEY", "stub-qdrant-key")
os.environ.setdefault("MEM0_API_KEY", "stub-mem0-key")
os.environ.setdefault("USE_LOCAL_STORAGE", "true")
os.environ.setdefault("APP_ENV", "test")
