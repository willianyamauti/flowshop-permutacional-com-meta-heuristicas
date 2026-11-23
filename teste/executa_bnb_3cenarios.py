# =============================================================================
# executa_bnb_3cenarios.py
# Executa exclusivamente o Branch-and-Bound Combinatório Exato nos Cenários
# 3, 4 e 5 com limite de 2h30min (9000s) por cenário, preservando os logs
# anteriores de GRASP e Simulated Annealing e atualizando as tabelas PNG.
# =============================================================================
import os
import time
from leitor_dados import carrega_cenario
from heuristicas import (
    avaliar_sequencia,
    construtiva_edd_setup,
    resolver_flowshop_bnb,
    gerar_grafico_gantt,
)
from gera_tabela_cenario import processar_cenario

# PARAMETRIZAÇÃO GLOBAL
C_ATRASO = 600.0
C_ESTOQUE = 180.0
N_MAQ = 4

# IMPORTANTE: False para manter os logs/Gantts do GRASP e SA já gerados
# na pasta resultados/cenario_X e atualizar apenas o B&B Exato + Tabela PNG.
LIMPAR_RESULTADOS_ANTERIORES = False

# Apenas os 3 cenários que atingiram timeout anteriormente (15, 25 e 20 OPs)
CENARIOS_ALVO = [3, 4, 5]

# 2 horas e 30 minutos = 9000 segundos por cenário (máximo 7h30min total)
TEMPO_LIMITE_SEGUNDOS = 9000

MATRIZ_SETUP = {
    'F1': {'F1': 0.0, 'F2': 2.0, 'F3': 3.0},
    'F2': {'F1': 3.5, 'F2': 0.0, 'F3': 1.5},
    'F3': {'F1': 4.0, 'F2': 2.5, 'F3': 0.0},
}

VIZ_PADRAO = ['insercao', 'swap', 'bloco']

CONFIGURACOES = [
    {
        "tipo_const": "edd",
        "alpha": 0.0,
        "algoritmo": "bnb",
        "time_limit": TEMPO_LIMITE_SEGUNDOS,
        "viz": VIZ_PADRAO,
    },
]


def _formatar_lista_viz(estruturas):
    mapa = {"insercao": "Inserção", "swap": "Swap", "bloco": "Bloco"}
    return " + ".join(mapa.get(v, v.capitalize()) for v in estruturas)


def executar_experimento(num_cenario, cfg, dados):
    """Executa o B&B Combinatório Exato para um cenário e atualiza os arquivos."""
    estruturas_viz = cfg["viz"]
    str_viz = _formatar_lista_viz(estruturas_viz)
    tl = cfg.get("time_limit", TEMPO_LIMITE_SEGUNDOS)

    inicio_tempo = time.perf_counter()

    # 1. SOLUÇÃO INICIAL (ESTRATÉGIA A: EDD + SETUP)
    nome_construtiva = "Estratégia A (EDD + Setup)"
    slug_construtiva = "edd"
    seq_inicial, log_const = construtiva_edd_setup(dados, MATRIZ_SETUP, peso_setup=5.0)
    custo_inicial = avaliar_sequencia(seq_inicial, dados, MATRIZ_SETUP, C_ATRASO, C_ESTOQUE, N_MAQ)

    # 2. OTIMIZAÇÃO EXATA VIA BRANCH-AND-BOUND COMBINATÓRIO
    nome_algoritmo = f"Branch-and-Bound Combinatório (TimeLimit={tl}s)"
    slug_algoritmo = "bnb_exato"
    seq_final, custo_final, iteracoes, log_ref = resolver_flowshop_bnb(
        dados,
        MATRIZ_SETUP,
        C_ATRASO,
        C_ESTOQUE,
        n_maq=N_MAQ,
        time_limit=tl,
        mostrar_progresso=True,
        seq_inicial=seq_inicial,
        usar_vnd_warmstart=True,
    )

    tempo_execucao = time.perf_counter() - inicio_tempo
    reducao_pct = ((custo_inicial - custo_final) / custo_inicial) * 100.0 if custo_inicial > 0 else 0.0

    # 3. DIRETÓRIOS E NOMES DE SAÍDA (MESMO PADRÃO DO SCRIPT PRINCIPAL)
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

    # 4. GERAÇÃO DO GANTT ATUALIZADO
    try:
        titulo = f"Gantt - Cenário {num_cenario} ({slug_construtiva.upper()} + {slug_algoritmo.upper()})"
        gerar_grafico_gantt(
            seq_final, dados, MATRIZ_SETUP, titulo, nome_png,
            c_atraso=C_ATRASO, c_estoque=C_ESTOQUE, n_maq=N_MAQ
        )
    except Exception as e:
        print(f"  [AVISO] Falha ao gerar Gantt ({nome_png}): {e}")

    # 5. SALVAMENTO DO LOG ATUALIZADO
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
        f"Custo: R$ {custo_final:,.2f} ({reducao_pct:.1f}%) | "
        f"Nós: {iteracoes:,} | Tempo: {tempo_execucao:.2f}s"
    )


def rodar_bnb_longo():
    print("=" * 72)
    print(f"   B&B COMBINATÓRIO EXATO: CENÁRIOS {CENARIOS_ALVO} (TimeLimit = {TEMPO_LIMITE_SEGUNDOS}s / 2h30min)")
    print("=" * 72)

    for num_cenario in CENARIOS_ALVO:
        nome_arquivo = f"cenario_{num_cenario}.csv"
        print(f"\n==================================================")
        print(f" PROCESSANDO CENÁRIO {num_cenario} ({nome_arquivo})")
        print(f"==================================================")

        try:
            dados = carrega_cenario(nome_arquivo)
        except Exception as e:
            print(f"[ERRO] Não foi possível carregar {nome_arquivo}: {e}")
            continue

        for cfg in CONFIGURACOES:
            executar_experimento(num_cenario, cfg, dados)

        print(f"\n[ATUALIZANDO TABELA] Reprocessando 'resultados/cenario_{num_cenario}'...")
        processar_cenario(num_cenario)

    print("\n" + "=" * 72)
    print("   EXECUÇÃO CONCLUÍDA! Logs B&B, Gantts e tabelas PNG atualizados.")
    print("=" * 72)


if __name__ == "__main__":
    rodar_bnb_longo()
