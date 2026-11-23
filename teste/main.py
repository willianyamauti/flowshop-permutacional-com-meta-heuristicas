# =============================================================================
# main.py
# =============================================================================
import os
import time
from leitor_dados import carrega_cenario
from heuristicas import (
    avaliar_sequencia,
    construtiva_edd_setup,
    construtiva_parcialmente_gulosa,
    vnd,
    grasp,
    simulated_annealing,
    resolver_flowshop_gurobi,
    resolver_flowshop_bnb,
    gerar_grafico_gantt,
)

# PARAMETRIZAÇÃO DO PROBLEMA
C_ATRASO = 600.0
C_ESTOQUE = 180.0
N_MAQ = 4

MATRIZ_SETUP = {
    'F1': {'F1': 0.0, 'F2': 2.0, 'F3': 3.0},
    'F2': {'F1': 3.5, 'F2': 0.0, 'F3': 1.5},
    'F3': {'F1': 4.0, 'F2': 2.5, 'F3': 0.0},
}


def _formatar_lista_viz(estruturas):
    mapa = {"insercao": "Inserção", "swap": "Swap", "bloco": "Bloco"}
    return " + ".join(mapa.get(v, v.capitalize()) for v in estruturas)


def menu_seletor():
    print("=" * 65)
    print("      SISTEMA DE OTIMIZAÇÃO FLOWSHOP PERMUTACIONAL             ")
    print("=" * 65)

    # 1. Seleção do Cenário
    print("\n[1] ESCOLHA O CENÁRIO:")
    for i in range(1, 6):
        print(f"  {i} - Cenário {i}")
    num_cenario = input("Digite o número do cenário (1-5): ").strip()
    nome_arquivo = f"cenario_{num_cenario}.csv"

    # 2. Seleção da Estratégia Construtiva
    print("\n[2] ESCOLHA A ESTRATÉGIA CONSTRUTIVA (SOLUÇÃO INICIAL):")
    print("  1 - Estratégia A: Regra de Despacho Composta (EDD + Tempo de Setup)")
    print("  2 - Estratégia B: Parcialmente Gulosa (RCL / GRASP alpha)")
    opcao_construtiva = input("Digite a opção da construtiva (1/2): ").strip()
    alpha = 0.3
    if opcao_construtiva == '2':
        try:
            alpha = float(input("Digite o Alfa desejado (ex: 0.3): ").strip().replace(",", "."))
        except ValueError:
            print("Valor inválido. Definindo alfa = 0.3 por padrão.")
            alpha = 0.3

    # 3. Seleção do Algoritmo / Estruturas de Vizinhança
    print("\n[3] ESCOLHA O MÉTODO DE REFINAMENTO / ALGORITMO:")
    print("  1 - VND (Apenas Swap)")
    print("  2 - VND (Apenas Inserção)")
    print("  3 - VND (Completa: Inserção + Swap + Bloco)")
    print("  4 - Gurobi Optimizer (Exato MILP + Warm Start VND)")
    print("  5 - Branch-and-Bound Combinatório Exato (Sem Big-M)")
    print("  6 - GRASP (Multi-Start: RCL + VND)")
    print("  7 - Simulated Annealing (Auto-Calibrado: Inserção + Swap + Bloco)")
    opcao_algoritmo = input("Digite a opção desejada (1-7): ").strip()

    time_limit_gurobi = 1800
    mip_gap_alvo = 0.05
    if opcao_algoritmo == '4':
        try:
            val_tempo = input("Tempo limite do Gurobi em segundos [Padrão: 1800 = 30 min]: ").strip()
            if val_tempo:
                time_limit_gurobi = max(1, int(val_tempo))
        except ValueError:
            print("Valor inválido. Definindo timeout = 1800s (30 min) por padrão.")
            time_limit_gurobi = 1800

        try:
            val_gap = input("Gap alvo de parada em % [Padrão: 5.0]: ").strip().replace(",", ".")
            if val_gap:
                mip_gap_alvo = max(0.0, float(val_gap) / 100.0)
        except ValueError:
            print("Valor inválido. Definindo gap alvo = 5.0% por padrão.")
            mip_gap_alvo = 0.05

    time_limit_bnb = 60
    if opcao_algoritmo == '5':
        try:
            val_bnb = input("Tempo limite do Branch-and-Bound em segundos [Padrão: 60]: ").strip()
            if val_bnb:
                time_limit_bnb = max(1, int(val_bnb))
        except ValueError:
            time_limit_bnb = 60

    max_iter_grasp = 100
    if opcao_algoritmo == '6':
        try:
            val = input("Número de iterações do GRASP [Padrão: 100]: ").strip()
            if val:
                max_iter_grasp = max(1, int(val))
        except ValueError:
            max_iter_grasp = 100

    mapa_viz = {
        '1': ['swap'],
        '2': ['insercao'],
        '3': ['insercao', 'swap', 'bloco'],
        '6': ['insercao', 'swap', 'bloco'],
        '7': ['insercao', 'swap', 'bloco'],
    }
    estruturas_selecionadas = mapa_viz.get(opcao_algoritmo, ['insercao', 'swap', 'bloco'])

    return (
        num_cenario,
        nome_arquivo,
        opcao_construtiva,
        alpha,
        opcao_algoritmo,
        estruturas_selecionadas,
        max_iter_grasp,
        time_limit_gurobi,
        mip_gap_alvo,
        time_limit_bnb,
    )


if __name__ == "__main__":
    (
        num_cenario,
        nome_arquivo,
        opcao_construtiva,
        alpha,
        opcao_algoritmo,
        estruturas_viz,
        max_iter_grasp,
        time_limit_gurobi,
        mip_gap_alvo,
        time_limit_bnb,
    ) = menu_seletor()

    dados = carrega_cenario(nome_arquivo)

    inicio_tempo = time.perf_counter()

    # -------------------------------------------------------------------------
    # GERAR SOLUÇÃO INICIAL
    # -------------------------------------------------------------------------
    if opcao_construtiva == '1':
        nome_construtiva = "Estratégia A (EDD + Setup)"
        seq_inicial, log_const = construtiva_edd_setup(dados, MATRIZ_SETUP, peso_setup=5.0)
    else:
        nome_construtiva = f"Estratégia B (Parcialmente Gulosa RCL alpha={alpha})"
        seq_inicial, log_const = construtiva_parcialmente_gulosa(
            dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, N_MAQ, alpha
        )

    custo_inicial = avaliar_sequencia(seq_inicial, dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, N_MAQ)

    # -------------------------------------------------------------------------
    # REFINAMENTO / RESOLUÇÃO
    # -------------------------------------------------------------------------
    iteracoes = 0
    if opcao_algoritmo == '4':
        nome_algoritmo = (
            f"Gurobi Optimizer (Exato MILP + Warm Start | "
            f"Gap<={mip_gap_alvo * 100:.1f}% | {time_limit_gurobi}s)"
        )
        str_viz = "Warm Start VND"
        seq_final, custo_final, iteracoes, log_ref = resolver_flowshop_gurobi(
            dados,
            MATRIZ_SETUP,
            C_ATRASO,
            C_ESTOQUE,
            n_maq=N_MAQ,
            time_limit=time_limit_gurobi,
            mip_gap_alvo=mip_gap_alvo,
            mostrar_progresso=True,
            verbose=False,
            seq_inicial=seq_inicial,
            usar_vnd_warmstart=True,
        )
    elif opcao_algoritmo == '5':
        nome_algoritmo = f"Branch-and-Bound Combinatório (TimeLimit={time_limit_bnb}s)"
        str_viz = _formatar_lista_viz(estruturas_viz)
        seq_final, custo_final, iteracoes, log_ref = resolver_flowshop_bnb(
            dados,
            MATRIZ_SETUP,
            C_ATRASO,
            C_ESTOQUE,
            n_maq=N_MAQ,
            time_limit=time_limit_bnb,
            mostrar_progresso=True,
            seq_inicial=seq_inicial,
            usar_vnd_warmstart=True,
        )
    elif opcao_algoritmo == '6':
        nome_algoritmo = f"GRASP (alpha={alpha}, iter={max_iter_grasp})"
        str_viz = _formatar_lista_viz(estruturas_viz)
        seq_final, custo_final, iteracoes, log_ref = grasp(
            dados,
            MATRIZ_SETUP,
            C_ATRASO,
            C_ESTOQUE,
            n_maq=N_MAQ,
            alpha=alpha,
            max_iter=max_iter_grasp,
            estruturas=estruturas_viz,
            seq_inicial=seq_inicial,
        )
    elif opcao_algoritmo == '7':
        nome_algoritmo = "Simulated Annealing"
        str_viz = _formatar_lista_viz(estruturas_viz)
        seq_final, custo_final, iteracoes, log_ref = simulated_annealing(
            seq_inicial,
            dados,
            MATRIZ_SETUP,
            C_ATRASO,
            C_ESTOQUE,
            n_maq=N_MAQ,
            temp_inicial=None,
            taxa_resfriamento=0.95,
            iter_por_temp=50,
            estruturas=estruturas_viz,
        )
    else:
        nome_algoritmo = "VND (Variable Neighborhood Descent)"
        str_viz = _formatar_lista_viz(estruturas_viz)
        seq_final, custo_final, iteracoes, log_ref = vnd(
            seq_inicial,
            dados,
            MATRIZ_SETUP,
            C_ATRASO,
            C_ESTOQUE,
            n_maq=N_MAQ,
            estruturas=estruturas_viz,
        )

    tempo_execucao = time.perf_counter() - inicio_tempo
    reducao_pct = ((custo_inicial - custo_final) / custo_inicial) * 100.0 if custo_inicial > 0 else 0.0

    # -------------------------------------------------------------------------
    # LOG COMPLETO DE RASTREAMENTO
    # -------------------------------------------------------------------------
    log_total = []
    log_total.extend(log_const)
    log_total.extend(log_ref)

    print("\n" + "=" * 65)
    print("            RASTREAMENTO PASSO A PASSO (LOG DE EXECUÇÃO)        ")
    print("=" * 65)
    for linha in log_total:
        print(linha)

    # -------------------------------------------------------------------------
    # RELATÓRIO DE DESEMPENHO NO TERMINAL
    # -------------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("                    RELATÓRIO DE EXECUÇÃO                    ")
    print("=" * 65)
    print(f" Cenário Analisado         : {nome_arquivo}")
    print(f" Estratégia Construtiva    : {nome_construtiva}")
    print(f" Algoritmo de Refinamento  : {nome_algoritmo}")
    print(f" Estruturas de Vizinhança  : {str_viz}")
    print("-" * 65)
    print(f" Custo Total Inicial       : R$ {custo_inicial:12.2f}")
    print(f" Custo Total Final         : R$ {custo_final:12.2f}")
    print(f" Percentual de Redução %   : {reducao_pct:11.2f}%")
    print(f" Tempo de Execução (s)     : {tempo_execucao:11.4f} s")
    print(f" Avaliações / Iterações    : {iteracoes:11d}")
    print("-" * 65)
    print(f" Sequência Final Encontrada: {' -> '.join(seq_final)}")
    print("=" * 65)

    # -------------------------------------------------------------------------
    # ORGANIZAÇÃO DE PASTAS E NOMES DINÂMICOS DE SAÍDA
    # -------------------------------------------------------------------------
    slug_construtiva = "edd" if opcao_construtiva == '1' else f"aleatorio_a{alpha}"

    if opcao_algoritmo == '4':
        slug_algoritmo = f"gurobi_ws_gap{int(round(mip_gap_alvo * 100))}"
    elif opcao_algoritmo == '5':
        slug_algoritmo = "bnb_exato"
    elif opcao_algoritmo == '6':
        slug_algoritmo = f"grasp_a{alpha}_it{max_iter_grasp}"
    elif opcao_algoritmo == '7':
        slug_algoritmo = "simulated_annealing"
    else:
        slug_algoritmo = "_".join(estruturas_viz)

    pasta_cenario = os.path.join("resultados", f"cenario_{num_cenario}")
    os.makedirs(pasta_cenario, exist_ok=True)

    nome_png = os.path.join(
        pasta_cenario,
        f"gantt_cenario{num_cenario}_{slug_construtiva}_{slug_algoritmo}.png"
    )
    nome_log = os.path.join(
        pasta_cenario,
        f"log_cenario{num_cenario}_{slug_construtiva}_{slug_algoritmo}.txt"
    )

    # -------------------------------------------------------------------------
    # GERAÇÃO DO GRÁFICO DE GANTT
    # -------------------------------------------------------------------------
    try:
        titulo = f"Gantt - Cenário {num_cenario} ({slug_construtiva.upper()} + {slug_algoritmo.upper()})"
        gerar_grafico_gantt(
            seq_final, dados, MATRIZ_SETUP, titulo, nome_png,
            c_atraso=C_ATRASO, c_estoque=C_ESTOQUE, n_maq=N_MAQ
        )
        print(f"\n[OK] Gráfico de Gantt salvo em '{nome_png}'.")
    except Exception as e:
        print(f"\n[AVISO] Falha ao gerar o Gantt: {e}")

    # -------------------------------------------------------------------------
    # SALVAMENTO DO ARQUIVO DE LOG
    # -------------------------------------------------------------------------
    with open(nome_log, 'w', encoding='utf-8') as f:
        for linha in log_total:
            f.write(linha + "\n")
        f.write("\n" + "=" * 65 + "\n")
        f.write("RESUMO FINAL DA EXECUÇÃO:\n")
        f.write(f"Cenário: {nome_arquivo}\n")
        f.write(f"Construtiva: {nome_construtiva}\n")
        f.write(f"Refinamento: {nome_algoritmo} ({str_viz})\n")
        f.write(f"Custo Inicial: R$ {custo_inicial:.2f}\n")
        f.write(f"Custo Final: R$ {custo_final:.2f}\n")
        f.write(f"Redução %: {reducao_pct:.2f}%\n")
        f.write(f"Tempo Execução: {tempo_execucao:.4f} s\n")
        f.write(f"Iterações: {iteracoes}\n")
        f.write(f"Sequência: {' -> '.join(seq_final)}\n")
        f.write(f"Gráfico Gantt: {nome_png}\n")
        f.write("=" * 65 + "\n")

    print(f"[OK] Rastreamento completo salvo em '{nome_log}'.")
