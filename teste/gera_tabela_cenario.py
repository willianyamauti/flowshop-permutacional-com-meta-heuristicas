# =============================================================================
# gera_tabela_cenario.py
# Leitor de logs e gerador automático de tabela comparativa com BKS e RPD (%).
# =============================================================================
import os
import re
import glob
import pandas as pd
import matplotlib.pyplot as plt


def _formatar_vizinhanca(texto_viz):
    """Padroniza os nomes das estruturas de vizinhança."""
    t = texto_viz.replace("insercao", "Inserção").replace("Insercao", "Inserção")
    t = t.replace("swap", "Swap").replace("bloco", "Bloco")
    return t.strip(" ()")


def extrair_metricas_log(caminho_arquivo):
    """Extrai os dados de desempenho do bloco de resumo do arquivo de log."""
    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        conteudo = f.read()

    match_resumo = re.search(r'RESUMO FINAL DA EXECUÇÃO:\n(.*?)={5,}', conteudo, re.DOTALL)
    if not match_resumo:
        return None

    resumo = match_resumo.group(1)

    construtiva = re.search(r'Construtiva:\s*(.*)', resumo)
    refinamento = re.search(r'Refinamento:\s*(.*)', resumo)
    custo_ini = re.search(r'Custo Inicial:\s*R\$\s*([\d\.]+)', resumo)
    custo_fim = re.search(r'Custo Final:\s*R\$\s*([\d\.]+)', resumo)
    reducao = re.search(r'Redução %:\s*([\d\.]+)', resumo)
    tempo = re.search(r'Tempo Execução:\s*([\d\.]+)', resumo)

    if not (construtiva and refinamento and custo_ini and custo_fim and reducao and tempo):
        return None

    str_const = construtiva.group(1).strip()
    str_ref = refinamento.group(1).strip()

    # 1. Identificação da Construtiva
    if "EDD" in str_const:
        pref_const = "EDD"
    elif "RCL" in str_const or "Gulosa" in str_const or "Parcialmente" in str_const:
        alpha_m = re.search(r'alpha=([\d\.]+)', str_const)
        alpha_val = alpha_m.group(1) if alpha_m else "0.3"
        pref_const = f"RCL (α={alpha_val})"
    else:
        pref_const = "Construtiva"

    blocos_paren = re.findall(r'\((.*?)\)', str_ref)
    otimo_provado = (
        "ÓTIMO GLOBAL COMPROVADO" in conteudo
        or "MIP Gap Final     : 0.00%" in conteudo
    )

    # 2. Identificação clara do Método e das Vizinhanças
    if "Branch-and-Bound" in str_ref:
        tag = "Ótimo Comprovado" if otimo_provado else "TimeLimit"
        metodo = f"Branch-and-Bound Exato [{tag}]"
    elif "Gurobi" in str_ref:
        tag = "Ótimo Comprovado" if otimo_provado else "MILP"
        metodo = f"Gurobi Optimizer [{tag}]"
    elif "GRASP" in str_ref:
        alpha_m = re.search(r'alpha=([\d\.]+)', str_ref)
        iter_m = re.search(r'iter=(\d+)', str_ref)
        a_str = f"α={alpha_m.group(1)}" if alpha_m else ""
        it_str = f"{iter_m.group(1)} it." if iter_m else ""
        params = ", ".join(p for p in [a_str, it_str] if p)

        viz_str = ""
        for b in blocos_paren:
            if "alpha=" not in b and "iter=" not in b:
                viz_str = _formatar_vizinhanca(b)
        viz_tag = f" [{viz_str}]" if viz_str else ""
        metodo = f"GRASP ({params}){viz_tag}" if params else f"GRASP{viz_tag}"
    elif "Simulated Annealing" in str_ref:
        viz_str = _formatar_vizinhanca(blocos_paren[-1]) if blocos_paren else ""
        viz_tag = f" [{viz_str}]" if viz_str else ""
        metodo = f"{pref_const} + Simulated Annealing{viz_tag}"
    elif "VND" in str_ref or "Variable Neighborhood" in str_ref:
        viz_validas = [
            _formatar_vizinhanca(b)
            for b in blocos_paren
            if "Variable Neighborhood Descent" not in b
        ]
        viz = viz_validas[-1] if viz_validas else "VND"
        metodo = f"{pref_const} + VND ({viz})"
    else:
        metodo = f"{pref_const} + {str_ref}"

    return {
        'Método / Refinamento': metodo,
        'Custo Total Inicial (R$)': float(custo_ini.group(1)),
        'Custo Total Final (R$)': float(custo_fim.group(1)),
        'Redução (%)': float(reducao.group(1)),
        'Tempo (s)': float(tempo.group(1)),
        'Ótimo Provado': otimo_provado,
    }


def _fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')


def gerar_imagem_tabela(df, caminho_saida, titulo_tabela, bks, tem_otimo_provado):
    """Renderiza um DataFrame como uma imagem PNG bem formatada via Matplotlib."""
    colunas = [
        'Método / Refinamento',
        'Custo Total Inicial',
        'Custo Total Final',
        'Redução (%)',
        'RPD (%)',
        'Tempo (s)',
    ]

    dados_tabela = []
    rpd_valores = []
    for _, row in df.iterrows():
        rpd = row['RPD (%)']
        rpd_valores.append(rpd)
        dados_tabela.append([
            row['Método / Refinamento'],
            _fmt_brl(row['Custo Total Inicial (R$)']),
            _fmt_brl(row['Custo Total Final (R$)']),
            f"{row['Redução (%)']:.2f}%".replace('.', ','),
            f"{rpd:.2f}%".replace('.', ','),
            f"{row['Tempo (s)']:.4f}".replace('.', ','),
        ])

    num_linhas = len(dados_tabela)
    altura = max(3.2, 1.5 + num_linhas * 0.48)
    fig, ax = plt.subplots(figsize=(14.5, altura), dpi=300)
    ax.axis('off')

    col_widths = [0.38, 0.13, 0.13, 0.12, 0.12, 0.12]

    tabela = ax.table(
        cellText=dados_tabela,
        colLabels=colunas,
        colWidths=col_widths,
        cellLoc='center',
        loc='center',
    )

    tabela.auto_set_font_size(False)
    tabela.set_fontsize(9.2)
    tabela.scale(1.0, 1.85)

    for (r, c), cell in tabela.get_celld().items():
        cell.set_edgecolor('#333333')
        cell.set_linewidth(0.8)

        if c == 0 and r > 0:
            cell.set_text_props(ha='left')
            cell.get_text().set_position((0.025, 0.5))

        if r == 0:
            cell.set_facecolor('#D3D3D3')
            cell.set_text_props(weight='bold', color='black', ha='center')
        else:
            is_best = rpd_valores[r - 1] <= 1e-4
            if is_best and c in (2, 4):
                cell.set_facecolor('#E6F4EA')
                cell.set_text_props(weight='bold', color='#137333')
            else:
                cell.set_facecolor('#F8F9FA' if r % 2 == 0 else '#FFFFFF')

    ref_label = "Ótimo Global Comprovado" if tem_otimo_provado else "Melhor Solução Conhecida (BKS)"
    subtitulo = f"Referência RPD ({ref_label}): {_fmt_brl(bks)}"
    plt.title(f"{titulo_tabela}\n{subtitulo}", fontsize=11.5, fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(caminho_saida, bbox_inches='tight', dpi=300)
    plt.close()


def processar_cenario(num_cenario, pasta_base="resultados"):
    """Lê os logs de um cenário, calcula BKS e RPD (%) e gera a tabela PNG."""
    pasta_cenario = os.path.join(pasta_base, f"cenario_{num_cenario}")

    if not os.path.exists(pasta_cenario):
        print(f"[ERRO] A pasta do cenário não existe: {pasta_cenario}")
        return

    padrao_logs = os.path.join(pasta_cenario, "log_*.txt")
    arquivos_log = sorted(glob.glob(padrao_logs))

    if not arquivos_log:
        print(f"[AVISO] Nenhum arquivo 'log_*.txt' encontrado em '{pasta_cenario}'.")
        return

    print(f"\n---> Lendo {len(arquivos_log)} arquivo(s) de log em '{pasta_cenario}'...")

    lista_dados = []
    for arq in arquivos_log:
        m = extrair_metricas_log(arq)
        if m:
            lista_dados.append(m)
            print(f"  [OK] Processado: {os.path.basename(arq)}")
        else:
            print(f"  [AVISO] Não foi possível extrair dados de: {os.path.basename(arq)}")

    if not lista_dados:
        print("[ERRO] Nenhuma métrica válida foi extraída.")
        return

    df = pd.DataFrame(lista_dados)
    bks = df['Custo Total Final (R$)'].min()
    tem_otimo_provado = bool(df['Ótimo Provado'].any())
    df['RPD (%)'] = df['Custo Total Final (R$)'].apply(
        lambda c: ((c - bks) / bks) * 100.0 if bks > 0 else 0.0
    )

    nome_imagem = f"tabela_comparativa_cenario_{num_cenario}.png"
    caminho_imagem = os.path.join(pasta_cenario, nome_imagem)

    titulo = f"Tabela Comparativa de Desempenho - Cenário {num_cenario}"
    gerar_imagem_tabela(df, caminho_imagem, titulo, bks, tem_otimo_provado)

    print(f"\n[SUCESSO] Tabela salva localmente em:")
    print(f"          -> {caminho_imagem}\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        num_c = sys.argv[1]
    else:
        num_c = input("Digite o número do cenário a processar (1-5) [Padrão: 1]: ").strip()
        if not num_c:
            num_c = "1"

    processar_cenario(num_c)
