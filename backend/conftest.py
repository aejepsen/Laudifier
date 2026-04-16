import sys
from pathlib import Path

# Adiciona o diretório pai de backend/ ao path para que
# os imports `from backend.xxx` funcionem ao rodar pytest de dentro de backend/
# e `from api.xxx` funcionem ao rodar de fora.
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
