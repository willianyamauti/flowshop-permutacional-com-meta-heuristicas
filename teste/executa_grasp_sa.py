# =============================================================================
# executa_tudo.py
# Automação de experimentos: Roda os 5 cenários comparando GRASP e
# Simulated Annealing (usando Swap + Inserção), gera logs, Gantts e tabelas PNG.
# =============================================================================
import os
import glob
import time
from leitor_dados import carrega_cenario
from heuristicas import (
    avaliar_sequencia,
    construtiva_edd_setup,
    construtiva_parcialmente_gulosa,
    grasp,
    simulated_annealing,
    gerar_grafico_gantt,
)
from gera_tabela_cenario import processar_cenario

# PARAMETRIZAÇÃO GLOBAL
C_ATRASO = 600.0
C_ESTOQUE = 180.0
N_MAQ = 4

# Se True, apaga logs/Gantts antigos da pasta do cenário antes de rodar,
# garantindo que a tabela PNG contenha apenas GRASP e Simulated Annealing.
LIMPAR_RESULTADOS_ANTERIORES = True

MATRIZ_SETUP = {
    'F1': {'F1': 0.0, 'F2': 2.0, 'F3': 3.0},
    'F2': {'F1': 3.5, 'F2': 0.0, 'F3': 1.5},
    'F3': {'F1': 4.0, 'F2': 2.5, 'F3': 0.0},
}

# CONFIGURAÇÕES A SEREM TESTADAS POR CENÁRIO (GRASP e Simulated Annealing)
CONFIGURACOES = [
    # GRASP (RCL + VND com Swap e Inserção)
    {
        "tipo_const": "rcl",
        "alpha": 0.3,
        "algoritmo": "grasp",
        "max_iter": 100,
        "viz": ['swap', 'insercao'],
    },
    {
        "tipo_const": "rcl",
        "alpha": 0.7,
        "algoritmo": "grasp",
        "max_iter": 100,
        "viz": ['swap', 'insercao'],
    },

    # Simulated Annealing (Partindo de EDD e de RCL, com Swap e Inserção)
    {
        "tipo_const": "edd",
        "alpha": 0.0,
        "algoritmo": "sa",
        "viz": ['swap', 'insercao'],
    },
    {
        "tipo_const": "rcl",
        "alpha": 0.3,
        "algoritmo": "sa",
        "viz": ['swap', 'insercao'],
    },
]


def executar_experimento(num_cenario, cfg, dados):
    """Executa uma combinação (Cenário x Meta-heurística) e salva os arquivos."""
    tipo_const = cfg["tipo_const"]
    alpha = cfg["alpha"]
    algoritmo = cfg["algoritmo"]
    estruturas_viz = cfg["viz"]
    str_viz = " + ".join([v.replace("insercao", "Inserção").capitalize() for v in estruturas_viz])

    inicio_tempo = time.perf_counter()

    # 1. SOLUÇÃO INICIAL (CONSTRUTIVA)
    if tipo_const == "edd":
        nome_construtiva = "Estratégia A (EDD + Setup)"
        slug_construtiva = "edd"
        seq_inicial, log_const = construtiva_edd_setup(dados, MATRIZ_SETUP, peso_setup=50.0)
    else:
        nome_construtiva = f"Estratégia B (Parcialmente Gulosa RCL alpha={alpha})"
        slug_construtiva = f"rcl_a{alpha}"
        seq_inicial, log_const = construtiva_parcialmente_gulosa(
            dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, N_MAQ, alpha
        )

    custo_inicial = avaliar_sequencia(seq_inicial, dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, N_MAQ)

    # 2. META-HEURÍSTICA (GRASP ou SIMULATED ANNEALING)
    if algoritmo == "grasp":
        max_iter = cfg.get("max_iter", 100)
        nome_algoritmo = f"GRASP (alpha={alpha}, iter={max_iter})"
        slug_algoritmo = f"grasp_a{alpha}_it{max_iter}"
        seq_final, custo_final, iteracoes, log_ref = grasp(
            dados,
            MATRIZ_SETUP,
            C_ATRASO,
            C_ESTOQUE,
            n_maq=N_MAQ,
            alpha=alpha,
            max_iter=max_iter,
            estruturas=estruturas_viz,
            seq_inicial=seq_inicial,
        )
    else:
        nome_algoritmo = "Simulated Annealing"
        slug_algoritmo = "simulated_annealing"
        seq_final, custo_final, iteracoes, log_ref = simulated_annealing(
            seq_inicial,
            dados,
            MATRIZ_SETUP,
            C_ATRASO,
            C_ESTOQUE,
            n_maq=N_MAQ,
            temp_inicial=2000.0,
            temp_final=1.0,
            taxa_resfriamento=0.95,
            iter_por_temp=50,
            estruturas=estruturas_viz,
        )

    tempo_execucao = time.perf_counter() - inicio_tempo
    reducao_pct = ((custo_inicial - custo_final) / custo_inicial) * 100.0 if custo_inicial > 0 else 0.0

    # 3. CRIAÇÃO DE DIRETÓRIOS E NOMES DE ARQUIVO
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

    # 4. GERAÇÃO DO GANTT
    try:
        titulo = f"Gantt - Cenário {num_cenario} ({slug_construtiva.upper()} + {slug_algoritmo.upper()})"
        gerar_grafico_gantt(
            seq_final, dados, MATRIZ_SETUP, titulo, nome_png,
            c_atraso=C_ATRASO, c_estoque=C_ESTOQUE, n_maq=N_MAQ
        )
    except Exception as e:
        print(f"  [AVISO] Falha ao gerar Gantt ({nome_png}): {e}")

    # 5. SALVAMENTO DO LOG
    log_total = log_const + log_ref
    with open(nome_log, 'w', encoding='utf-8') as f:
        for linha in log_total:
            f.write(linha + "\n")
        f.write("\n" + "=" * 65 + "\n")
        f.write("RESUMO FINAL DA EXECUÇÃO:\n")
        f.write(f"Cenário: cenario_{num_cenario}.csv\n")
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

    print(
        f"  [OK] {slug_construtiva} + {slug_algoritmo} ({str_viz}) | "
        f"Custo: R$ {custo_final:,.2f} ({reducao_pct:.1f}%) | Tempo: {tempo_execucao:.4f}s"
    )


def rodar_bateria_completa():
    total_cfg = len(CONFIGURACOES)
    print("=" * 70)
    print(f"   BATERIA DE EXPERIMENTOS: GRASP & SIMULATED ANNEALING (5x{total_cfg})")
    print("=" * 70)

    for num_cenario in range(1, 6):
        nome_arquivo = f"cenario_{num_cenario}.csv"
        print(f"\n==================================================")
        print(f" PROCESSANDO CENÁRIO {num_cenario} ({nome_arquivo})")
        print(f"==================================================")

        try:
            dados = carrega_cenario(nome_arquivo)
        except Exception as e:
            print(f"[ERRO] Não foi possível carregar {nome_arquivo}: {e}")
            continue

        pasta_cenario = os.path.join("resultados", f"cenario_{num_cenario}")
        if LIMPAR_RESULTADOS_ANTERIORES and os.path.exists(pasta_cenario):
            for padrao in ("log_cenario*.txt", "gantt_cenario*.png"):
                for arq_antigo in glob.glob(os.path.join(pasta_cenario, padrao)):
                    os.remove(arq_antigo)

        for i, cfg in enumerate(CONFIGURACOES, start=1):
            print(f"-> Executando Teste {i}/{total_cfg}...")
            executar_experimento(num_cenario, cfg, dados)

        print(f"\n[GERANDO TABELA] Processando resultados de 'resultados/cenario_{num_cenario}'...")
        processar_cenario(num_cenario)

    print("\n" + "=" * 70)
    print("   BATERIA CONCLUÍDA! Logs, Gantts e tabelas PNG atualizados.")
    print("=" * 70)


if __name__ == "__main__":
    rodar_bateria_completa()