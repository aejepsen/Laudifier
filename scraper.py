"""
Scraper do Compêndio da Radiologia (Google Sites).
Extrai texto de todas as páginas e salva em data/raw/<slug>.txt
"""
import os
import re
import time
import json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.compendioradiologia.com"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
INDEX_FILE = os.path.join(os.path.dirname(__file__), "data", "index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def url_to_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "home"
    slug = re.sub(r"[^\w\-]", "_", path.replace("/", "__"))
    return slug[:120]


def extract_text(page) -> str:
    """Extrai texto limpo do body, sem scripts/styles."""
    return page.evaluate("""() => {
        const clone = document.body.cloneNode(true);
        // Remover scripts, styles, nav, footer
        ['script','style','noscript','nav','footer'].forEach(tag => {
            clone.querySelectorAll(tag).forEach(el => el.remove());
        });
        // Remover elementos ocultos
        clone.querySelectorAll('[style*="display:none"],[style*="display: none"],[hidden]').forEach(el => el.remove());
        return clone.innerText;
    }""")


def get_all_links(page) -> list[str]:
    """Coleta todos os links internos da página."""
    links = page.eval_on_selector_all(
        "a[href]",
        f"els => els.map(e => e.href).filter(h => h.includes('compendioradiologia.com') && !h.includes('#'))"
    )
    seen = set()
    result = []
    for l in links:
        clean = l.split("?")[0].split("#")[0].rstrip("/")
        if clean and clean not in seen and clean != BASE_URL:
            seen.add(clean)
            result.append(clean)
    return result


def scrape():
    index = []
    visited = set()
    queue = [BASE_URL]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (compatible; Laudifier/1.0)"
        )

        # Descobrir todas as páginas navegando pelo site
        print("=== Fase 1: Descobrindo páginas ===")
        discovery_page = context.new_page()
        discovery_page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        initial_links = get_all_links(discovery_page)
        discovery_page.close()

        all_urls = list({BASE_URL} | set(initial_links))
        print(f"URLs descobertas: {len(all_urls)}")

        # Scraper de cada página
        print("\n=== Fase 2: Extraindo conteúdo ===")
        scrape_page = context.new_page()

        for i, url in enumerate(sorted(all_urls)):
            if url in visited:
                continue
            visited.add(url)

            slug = url_to_slug(url)
            out_path = os.path.join(OUTPUT_DIR, f"{slug}.txt")

            try:
                scrape_page.goto(url, wait_until="networkidle", timeout=25000)
                time.sleep(1)  # aguarda JS extra
                text = extract_text(scrape_page)

                # Limpar texto
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                lines = [l for l in lines if len(l) > 2]
                # Remover duplicatas consecutivas
                clean_lines = [lines[0]] if lines else []
                for line in lines[1:]:
                    if line != clean_lines[-1]:
                        clean_lines.append(line)

                content = "\n".join(clean_lines)

                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(f"URL: {url}\n")
                    f.write(f"SLUG: {slug}\n")
                    f.write("=" * 60 + "\n")
                    f.write(content)

                word_count = len(content.split())
                print(f"[{i+1:3}/{len(all_urls)}] OK  {slug[:60]:<60} {word_count:>6} palavras")

                index.append({
                    "url": url,
                    "slug": slug,
                    "file": f"data/raw/{slug}.txt",
                    "words": word_count,
                })

                # Descobrir mais links nesta página
                new_links = get_all_links(scrape_page)
                for nl in new_links:
                    nl_clean = nl.split("?")[0].rstrip("/")
                    if nl_clean not in visited and nl_clean not in all_urls:
                        all_urls.append(nl_clean)

            except Exception as e:
                print(f"[{i+1:3}/{len(all_urls)}] ERR {slug[:60]:<60} {str(e)[:60]}")

            time.sleep(0.5)  # rate limiting gentil

        scrape_page.close()
        browser.close()

    # Salvar índice
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    total_words = sum(p["words"] for p in index)
    print(f"\n=== Concluído ===")
    print(f"Páginas: {len(index)}")
    print(f"Total palavras: {total_words:,}")
    print(f"Índice salvo em: {INDEX_FILE}")


if __name__ == "__main__":
    scrape()
