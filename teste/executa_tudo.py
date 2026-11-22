# =============================================================================
# executa_tudo.py
# Automação completa de experimentos: Roda os 5 cenários x 7 configurações,
# gera os logs, gráficos de Gantt e imagens das tabelas comparativas em PNG.
# =============================================================================
import os
import time
from leitor_dados import carrega_cenario
from heuristicas import (
    avaliar_sequencia,
    construtiva_edd_setup,
    construtiva_parcialmente_gulosa,
    vnd,
    resolver_flowshop_gurobi,
    gerar_grafico_gantt,
)
from gera_tabela_cenario import processar_cenario

# PARAMETRIZAÇÃO GLOBAL
C_ATRASO = 600.0
C_ESTOQUE = 180.0
N_MAQ = 4
ALPHA_DEFAULT = 0.7

MATRIZ_SETUP = {
    'F1': {'F1': 0.0, 'F2': 2.0, 'F3': 3.0},
    'F2': {'F1': 3.5, 'F2': 0.0, 'F3': 1.5},
    'F3': {'F1': 4.0, 'F2': 2.5, 'F3': 0.0},
}

# DEFINE AS 7 CONFIGURAÇÕES A SEREM TESTADAS POR CENÁRIO
CONFIGURACOES = [
    # Estratégia A (EDD + Setup)
    {"tipo_const": "edd", "alpha": 0.0, "algoritmo": "vnd", "viz": ['swap']},
    {"tipo_const": "edd", "alpha": 0.0, "algoritmo": "vnd", "viz": ['insercao']},
    {"tipo_const": "edd", "alpha": 0.0, "algoritmo": "vnd", "viz": ['swap', 'insercao']},
    
    # Estratégia B (Parcialmente Gulosa / RCL alpha=0.3)
    {"tipo_const": "rcl", "alpha": ALPHA_DEFAULT, "algoritmo": "vnd", "viz": ['swap']},
    {"tipo_const": "rcl", "alpha": ALPHA_DEFAULT, "algoritmo": "vnd", "viz": ['insercao']},
    {"tipo_const": "rcl", "alpha": ALPHA_DEFAULT, "algoritmo": "vnd", "viz": ['swap', 'insercao']},
    
    # Modelo Exato MILP via Gurobi
    {"tipo_const": "edd", "alpha": 0.0, "algoritmo": "gurobi", "viz": []},
]


def executar_experimento(num_cenario, cfg, dados):
    """Executa uma única combinação (Cenário x Configuração) e salva os arquivos."""
    tipo_const = cfg["tipo_const"]
    alpha = cfg["alpha"]
    algoritmo = cfg["algoritmo"]
    estruturas_viz = cfg["viz"]

    inicio_tempo = time.perf_counter()

    # 1. GERAÇÃO DA SOLUÇÃO INICIAL (CONSTRUTIVA)
    if tipo_const == "edd":
        nome_construtiva = "Estratégia A (EDD + Setup)"
        slug_construtiva = "edd"
        seq_inicial, log_const = construtiva_edd_setup(dados, MATRIZ_SETUP, peso_setup=50.0)
    else:
        nome_construtiva = f"Estratégia B (Parcialmente Gulosa RCL alpha={alpha})"
        slug_construtiva = f"aleatorio_a{alpha}"
        seq_inicial, log_const = construtiva_parcialmente_gulosa(
            dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, N_MAQ, alpha
        )

    custo_inicial = avaliar_sequencia(seq_inicial, dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, N_MAQ)

    # 2. REFINAMENTO / OTIMIZAÇÃO EXATA
    if algoritmo == "gurobi":
        nome_algoritmo = "Gurobi Optimizer (Exato MILP)"
        slug_algoritmo = "gurobi"
        str_viz = "N/A (Modelo Exato)"
        seq_final, custo_final, iteracoes, log_ref = resolver_flowshop_gurobi(
            dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, n_maq=N_MAQ, time_limit=60
        )
    else:
        nome_algoritmo = "VND (Variable Neighborhood Descent)"
        slug_algoritmo = "_".join(estruturas_viz)
        str_viz = " + ".join([v.capitalize() for v in estruturas_viz])
        seq_final, custo_final, iteracoes, log_ref = vnd(
            seq_inicial, dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE,
            n_maq=N_MAQ, estruturas=estruturas_viz
        )

    tempo_execucao = time.perf_counter() - inicio_tempo
    reducao_pct = ((custo_inicial - custo_final) / custo_inicial) * 100.0 if custo_inicial > 0 else 0.0

    # 3. CRIAÇÃO DE DIRETÓRIOS E DEFINIÇÃO DOS NOMES DE ARQUIVO
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

    # 5. SALVAMENTO DO LOG DE EXECUÇÃO
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

    print(f"  [OK] {slug_construtiva} + {slug_algoritmo} | Custo: R$ {custo_final:,.2f} ({reducao_pct:.1f}%) | Tempo: {tempo_execucao:.4f}s")


def rodar_bateria_completa():
    print("=" * 70)
    print("   INICIANDO BATERIA AUTOMÁTICA DE EXPERIMENTOS (5 CENÁRIOS x 7 CONFIGS)")
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

        # Executa as 7 configurações para o cenário atual
        for i, cfg in enumerate(CONFIGURACOES, start=1):
            print(f"-> Executando Teste {i}/7...")
            executar_experimento(num_cenario, cfg, dados)

        # Gera automaticamente a tabela comparativa em PNG para este cenário
        print(f"\n[GERANDO TABELA] Processando resultados da pasta 'resultados/cenario_{num_cenario}'...")
        processar_cenario(num_cenario)

    print("\n" + "=" * 70)
    print("   BATERIA DE EXPERIMENTOS CONCLUÍDA COM SUCESSO!")
    print("   Todos os logs, gráficos de Gantt e tabelas PNG foram salvos.")
    print("=" * 70)


if __name__ == "__main__":
    rodar_bateria_completa()