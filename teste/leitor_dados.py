# =============================================================================
# leitor_dados_teste.py
# Igual ao leitor_dados.py original, mas robusto:
#   - Aceita cenario1.csv E cenario_1.csv
#   - Aceita ',' e ';', decimal com ponto ou vírgula
#   - UTF-8 com BOM
#   - Ignora cabeçalho textual
# =============================================================================
import csv
from pathlib import Path

CAMINHO_CENARIOS = Path(__file__).parent / "cenarios"


def _para_float(texto):
    """Converte '2.5' ou '2,5' (decimal brasileiro) em float."""
    return float(str(texto).strip().replace(",", "."))


def _achar_arquivo(nome_cenario):
    """Resolve cenario1.csv ou cenario_1.csv na pasta de cenários."""
    caminho = CAMINHO_CENARIOS / nome_cenario
    if caminho.exists():
        return caminho

    num = "".join(c for c in Path(nome_cenario).stem if c.isdigit())
    if num:
        for padrao in ("cenario{num}.csv", "cenario_{num}.csv",
                       "Cenario{num}.csv", "Cenario_{num}.csv"):
            tent = CAMINHO_CENARIOS / padrao.format(num=num)
            if tent.exists():
                return tent

        if CAMINHO_CENARIOS.exists():
            for arq in sorted(CAMINHO_CENARIOS.glob("*.csv")):
                if "cenario" in arq.stem.lower() and num in arq.stem:
                    return arq

    raise FileNotFoundError(f"Cenário não encontrado: {caminho}")


def carrega_cenario(nome_cenario, caminho_base=None):
    """Carrega o CSV do cenário e devolve a lista de OPs (formato original)."""
    if caminho_base is not None:
        caminho = Path(caminho_base) / nome_cenario
        if not caminho.exists():
            num = "".join(c for c in Path(nome_cenario).stem if c.isdigit())
            for padrao in ("cenario{num}.csv", "cenario_{num}.csv"):
                tent = Path(caminho_base) / padrao.format(num=num)
                if tent.exists():
                    caminho = tent
                    break
    else:
        caminho = _achar_arquivo(nome_cenario)

    lista_ops = []
    n_maq = None
    with open(caminho, mode="r", encoding="utf-8-sig", newline="") as arq:
        for n_linha, bruta in enumerate(arq, start=1):
            texto = bruta.strip()
            if not texto or texto.startswith("#"):
                continue

            delim = ";" if ";" in texto else ","
            campos = [c.strip() for c in next(csv.reader([texto], delimiter=delim))]
            if not campos:
                continue

            try:
                p = [_para_float(c) for c in campos[2:-1]]
                d = _para_float(campos[-1])
            except ValueError:
                if not lista_ops:
                    continue
                raise ValueError(f"{caminho.name}, linha {n_linha}: valor inválido: {texto!r}")

            if n_maq is None:
                n_maq = len(p)
            elif len(p) != n_maq:
                raise ValueError(f"{caminho.name}, linha {n_linha}: esperava {n_maq} tempos.")

            lista_ops.append({
                "op": campos[0],
                "familia": campos[1],
                "p": p,
                "d": d,
            })

    if not lista_ops:
        raise ValueError(f"{caminho.name}: nenhuma OP lida.")
    return lista_ops