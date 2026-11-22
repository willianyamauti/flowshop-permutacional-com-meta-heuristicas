# =============================================================================
# heuristicas.py
# =============================================================================
import math
import random
import os
import sys
import time
import gurobipy as gp
from gurobipy import GRB


def avaliar_sequencia(seq, dados, matriz_setup, c_atraso, c_estoque, n_maq=4):
    """Simula o sequenciamento e calcula o Custo Total (Atraso + Estoque)."""
    ops_dict = {x['op']: x for x in dados}
    n = len(seq)

    C = [[0.0] * n_maq for _ in range(n)]

    for k in range(n):
        op_curr = seq[k]
        dados_curr = ops_dict[op_curr]
        p_curr = dados_curr['p']

        if k == 0:
            C[0][0] = p_curr[0]
            for m in range(1, n_maq):
                C[0][m] = C[0][m - 1] + p_curr[m]
        else:
            op_prev = seq[k - 1]
            fam_prev = ops_dict[op_prev]['familia']
            fam_curr = dados_curr['familia']
            setup_time = matriz_setup[fam_prev][fam_curr]

            C[k][0] = C[k - 1][0] + setup_time + p_curr[0]
            for m in range(1, n_maq):
                C[k][m] = max(C[k][m - 1], C[k - 1][m] + setup_time) + p_curr[m]

    custo_total = 0.0
    for k in range(n):
        op = seq[k]
        d_j = ops_dict[op]['d']
        c_final = C[k][n_maq - 1]
        atraso = max(0.0, c_final - d_j)
        estoque = max(0.0, d_j - c_final)
        custo_total += (c_atraso * atraso) + (c_estoque * estoque)

    return custo_total


# -----------------------------------------------------------------------------
# ESTRATÉGIAS CONSTRUTIVAS
# -----------------------------------------------------------------------------
def construtiva_edd_setup(dados, matriz_setup, peso_setup=50.0):
    """Estratégia A: EDD ponderado pelo tempo de setup entre famílias."""
    log = ["=== CONSTRUÇÃO: ESTRATÉGIA A (EDD + SETUP) ==="]
    nao_agendados = dados.copy()
    seq = []

    nao_agendados.sort(key=lambda x: x['d'])
    primeira = nao_agendados.pop(0)
    seq.append(primeira['op'])
    fam_anterior = primeira['familia']
    log.append(f"Passo 1: Selecionada 1ª OP pelo menor Due Date: "
               f"{primeira['op']} (Família {fam_anterior}, d_j = {primeira['d']}h)")

    passo = 2
    while nao_agendados:
        melhor_cand = None
        melhor_score = float('inf')

        for cand in nao_agendados:
            fam_cand = cand['familia']
            setup = matriz_setup[fam_anterior][fam_cand]
            score = cand['d'] + (peso_setup * setup)

            if score < melhor_score:
                melhor_score = score
                melhor_cand = cand

        seq.append(melhor_cand['op'])
        log.append(f"Passo {passo}: Adicionada OP {melhor_cand['op']} "
                   f"(Família {melhor_cand['familia']}, Score = {melhor_score:.2f})")
        fam_anterior = melhor_cand['familia']
        nao_agendados.remove(melhor_cand)
        passo += 1

    return seq, log


def construtiva_parcialmente_gulosa(dados, matriz_setup, c_atraso, c_estoque, n_maq, alpha):
    """Estratégia B: Parcialmente Gulosa (RCL / GRASP)."""
    log = [f"=== CONSTRUÇÃO: ESTRATÉGIA B (PARCIALMENTE GULOSA - RCL alpha={alpha}) ==="]
    nao_agendados = [x['op'] for x in dados]
    seq = []

    passo = 1
    while nao_agendados:
        custos_candidatos = []
        for cand in nao_agendados:
            seq_teste = seq + [cand]
            custo = avaliar_sequencia(seq_teste, dados, matriz_setup, c_atraso, c_estoque, n_maq)
            custos_candidatos.append((cand, custo))

        custos_candidatos.sort(key=lambda x: x[1])
        c_min = custos_candidatos[0][1]
        c_max = custos_candidatos[-1][1]
        limite = c_min + alpha * (c_max - c_min)
        rcl = [cand for cand, custo in custos_candidatos if custo <= limite]

        escolhido = random.choice(rcl)
        seq.append(escolhido)
        nao_agendados.remove(escolhido)
        log.append(f"Passo {passo}: C_min=R${c_min:.2f}, C_max=R${c_max:.2f}, "
                   f"Limite RCL=R${limite:.2f} | Tamanho RCL={len(rcl)} | Escolhida: {escolhido}")
        passo += 1

    return seq, log


# -----------------------------------------------------------------------------
# ESTRUTURAS DE VIZINHANÇA
# -----------------------------------------------------------------------------
def gerar_vizinhos_swap(seq):
    vizinhos = []
    n = len(seq)
    for i in range(n):
        for j in range(i + 1, n):
            vizinho = seq.copy()
            vizinho[i], vizinho[j] = vizinho[j], vizinho[i]
            mov_desc = f"Swap pos ({i} <-> {j}): {seq[i]} <-> {seq[j]}"
            vizinhos.append((vizinho, mov_desc))
    return vizinhos


def gerar_vizinhos_insercao(seq):
    vizinhos = []
    n = len(seq)
    for i in range(n):
        for j in range(n):
            if i != j:
                vizinho = seq.copy()
                elem = vizinho.pop(i)
                vizinho.insert(j, elem)
                mov_desc = f"Inserção: Mover {elem} da pos {i} para pos {j}"
                vizinhos.append((vizinho, mov_desc))
    return vizinhos


OBTER_VIZINHOS = {
    'swap': gerar_vizinhos_swap,
    'insercao': gerar_vizinhos_insercao,
}


# -----------------------------------------------------------------------------
# BUSCA LOCAL & VND
# -----------------------------------------------------------------------------
def hill_climbing(seq_inicial, dados, matriz_setup, c_atraso, c_estoque,
                  n_maq=4, estrutura='swap'):
    log_sub = []
    seq_atual = seq_inicial.copy()
    custo_atual = avaliar_sequencia(seq_atual, dados, matriz_setup, c_atraso, c_estoque, n_maq)

    func_vizinhos = OBTER_VIZINHOS[estrutura]
    melhorou = True
    iter_count = 0

    while melhorou:
        melhorou = False
        vizinhos = func_vizinhos(seq_atual)

        for vizinho, mov_desc in vizinhos:
            iter_count += 1
            custo_viz = avaliar_sequencia(vizinho, dados, matriz_setup, c_atraso, c_estoque, n_maq)

            if custo_viz < custo_atual - 1e-6:
                diff = custo_atual - custo_viz
                log_sub.append(f"  [Iteração {iter_count}] MELHORA ENCONTRADA! {mov_desc} | "
                               f"Custo: R$ {custo_atual:.2f} -> R$ {custo_viz:.2f} (-R$ {diff:.2f})")
                custo_atual = custo_viz
                seq_atual = vizinho
                melhorou = True
                break

    return seq_atual, custo_atual, iter_count, log_sub


def vnd(seq_inicial, dados, matriz_setup, c_atraso, c_estoque, n_maq=4, estruturas=None):
    if estruturas is None or len(estruturas) == 0:
        estruturas = ['swap', 'insercao']

    log_vnd = ["\n=== REFINAMENTO: VARIABLE NEIGHBORHOOD DESCENT (VND) ==="]
    seq_atual = seq_inicial.copy()
    custo_atual = avaliar_sequencia(seq_atual, dados, matriz_setup, c_atraso, c_estoque, n_maq)
    log_vnd.append(f"Custo de Partida para o VND: R$ {custo_atual:.2f}\n")

    k = 0
    total_iteracoes = 0
    passo_vnd = 1

    while k < len(estruturas):
        nome_viz = estruturas[k]
        log_vnd.append(f"--- [Etapa {passo_vnd}] Explorando Vizinhança N{k + 1}: {nome_viz.upper()} ---")

        seq_linha, custo_linha, sub_iter, sub_log = hill_climbing(
            seq_atual, dados, matriz_setup, c_atraso, c_estoque, n_maq, estrutura=nome_viz
        )
        total_iteracoes += sub_iter
        log_vnd.extend(sub_log)

        if custo_linha < custo_atual - 1e-6:
            ganho = custo_atual - custo_linha
            log_vnd.append(f"==> SUCESSO em N{k + 1} ({nome_viz.upper()}): Custo reduzido para "
                           f"R$ {custo_linha:.2f} (-R$ {ganho:.2f}). Reiniciando para N1 (SWAP).\n")
            seq_atual = seq_linha
            custo_atual = custo_linha
            k = 0
        else:
            log_vnd.append(f"==> SEM MELHORIAS em N{k + 1} ({nome_viz.upper()}). "
                           f"Avançando para próxima vizinhança.\n")
            k += 1

        passo_vnd += 1

    log_vnd.append("Fim do VND: Nenhuma vizinhança possui soluções melhores. Ótimo Local atingido!")
    return seq_atual, custo_atual, total_iteracoes, log_vnd


# -----------------------------------------------------------------------------
# META-HEURÍSTICA: GRASP (RCL + VND)
# -----------------------------------------------------------------------------
def grasp(dados, matriz_setup, c_atraso, c_estoque, n_maq=4,
          alpha=0.3, max_iter=30, estruturas=None, seq_inicial=None):
    """
    Greedy Randomized Adaptive Search Procedure (GRASP):
    Alterna construção aleatorizada gulosa (RCL) e busca local (VND).
    """
    if estruturas is None or len(estruturas) == 0:
        estruturas = ['swap', 'insercao']

    log_grasp = [
        f"\n=== META-HEURÍSTICA: GRASP (alpha={alpha}, max_iter={max_iter}, VND={estruturas}) ==="
    ]

    melhor_seq = None
    melhor_custo = float('inf')
    total_iteracoes = 0

    # Caso uma solução inicial já tenha sido fornecida pelo menu, avalia e refina na iter 0
    if seq_inicial is not None:
        c_ini = avaliar_sequencia(seq_inicial, dados, matriz_setup, c_atraso, c_estoque, n_maq)
        seq_ref, custo_ref, sub_iter, _ = vnd(
            seq_inicial, dados, matriz_setup, c_atraso, c_estoque,
            n_maq=n_maq, estruturas=estruturas
        )
        total_iteracoes += sub_iter
        melhor_seq = seq_ref.copy()
        melhor_custo = custo_ref
        log_grasp.append(
            f"[Iteração 0 - Base] Construída: R$ {c_ini:.2f} -> Pós-VND: R$ {custo_ref:.2f}"
        )

    for it in range(1, max_iter + 1):
        seq_cand, _ = construtiva_parcialmente_gulosa(
            dados, matriz_setup, c_atraso, c_estoque, n_maq, alpha
        )
        custo_cand = avaliar_sequencia(seq_cand, dados, matriz_setup, c_atraso, c_estoque, n_maq)

        seq_ref, custo_ref, sub_iter, _ = vnd(
            seq_cand, dados, matriz_setup, c_atraso, c_estoque,
            n_maq=n_maq, estruturas=estruturas
        )
        total_iteracoes += sub_iter

        if custo_ref < melhor_custo - 1e-6:
            ganho = melhor_custo - custo_ref if melhor_custo < float('inf') else 0.0
            melhor_custo = custo_ref
            melhor_seq = seq_ref.copy()
            log_grasp.append(
                f"[Iteração {it:02d}/{max_iter}] NOVO MELHOR! RCL: R$ {custo_cand:.2f} -> "
                f"VND: R$ {custo_ref:.2f}" + (f" (-R$ {ganho:.2f})" if ganho > 0 else "")
            )
        else:
            log_grasp.append(
                f"[Iteração {it:02d}/{max_iter}] RCL: R$ {custo_cand:.2f} -> "
                f"VND: R$ {custo_ref:.2f} (Melhor global: R$ {melhor_custo:.2f})"
            )

    log_grasp.append(f"\nFim do GRASP: Melhor custo encontrado = R$ {melhor_custo:.2f}")
    return melhor_seq, melhor_custo, total_iteracoes, log_grasp


# -----------------------------------------------------------------------------
# META-HEURÍSTICA: SIMULATED ANNEALING (SA)
# -----------------------------------------------------------------------------
def _gerar_vizinho_aleatorio(seq, estruturas):
    """Gera um único vizinho aleatório em O(n) escolhendo entre swap e inserção."""
    n = len(seq)
    viz = seq.copy()
    if n < 2:
        return viz, "Sem movimento"

    est = random.choice(estruturas)
    i, j = random.sample(range(n), 2)

    if est == 'swap':
        viz[i], viz[j] = viz[j], viz[i]
        return viz, f"Swap ({i} <-> {j})"
    else:
        elem = viz.pop(i)
        viz.insert(j, elem)
        return viz, f"Inserção ({i} -> {j})"


def simulated_annealing(seq_inicial, dados, matriz_setup, c_atraso, c_estoque,
                        n_maq=4, temp_inicial=2000.0, temp_final=1.0,
                        taxa_resfriamento=0.95, iter_por_temp=50, estruturas=None):
    """
    Simulated Annealing (SA) para Flowshop Permutacional com Setup.
    """
    if estruturas is None or len(estruturas) == 0:
        estruturas = ['swap', 'insercao']

    seq_atual = seq_inicial.copy()
    custo_atual = avaliar_sequencia(seq_atual, dados, matriz_setup, c_atraso, c_estoque, n_maq)

    melhor_seq = seq_atual.copy()
    melhor_custo = custo_atual

    log_sa = [
        f"\n=== META-HEURÍSTICA: SIMULATED ANNEALING (T0={temp_inicial}, Tf={temp_final}, "
        f"alpha={taxa_resfriamento}, L={iter_por_temp}) ===",
        f"Custo Inicial: R$ {custo_atual:.2f}\n"
    ]

    temp = temp_inicial
    total_iteracoes = 0
    aceitos_piora = 0
    ciclo = 0

    while temp > temp_final:
        ciclo += 1
        melhorou_no_ciclo = False

        for _ in range(iter_por_temp):
            total_iteracoes += 1
            vizinho, mov_desc = _gerar_vizinho_aleatorio(seq_atual, estruturas)
            custo_viz = avaliar_sequencia(vizinho, dados, matriz_setup, c_atraso, c_estoque, n_maq)
            delta = custo_viz - custo_atual

            if delta < -1e-6 or random.random() < math.exp(-delta / temp):
                if delta >= -1e-6:
                    aceitos_piora += 1
                seq_atual = vizinho
                custo_atual = custo_viz

                if custo_atual < melhor_custo - 1e-6:
                    ganho = melhor_custo - custo_atual
                    melhor_custo = custo_atual
                    melhor_seq = seq_atual.copy()
                    melhorou_no_ciclo = True
                    log_sa.append(
                        f"  [Ciclo {ciclo:03d} | T={temp:7.2f}] NOVO MELHOR ({mov_desc}): "
                        f"R$ {melhor_custo:.2f} (-R$ {ganho:.2f})"
                    )

        if not melhorou_no_ciclo and ciclo % 15 == 0:
            log_sa.append(
                f"  [Ciclo {ciclo:03d} | T={temp:7.2f}] Custo atual: R$ {custo_atual:.2f} | "
                f"Melhor global: R$ {melhor_custo:.2f}"
            )

        temp *= taxa_resfriamento

    log_sa.append(
        f"\nFim do Simulated Annealing: Melhor custo = R$ {melhor_custo:.2f} "
        f"(Movimentos de piora aceitos: {aceitos_piora})"
    )
    return melhor_seq, melhor_custo, total_iteracoes, log_sa


# -----------------------------------------------------------------------------
# MÉTODO EXATO - GUROBI (ACELERADO COM WARM START HEURÍSTICO + CUTOFF)
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# MÉTODO EXATO - GUROBI (WARM START VND + BARRA DE PROGRESSO + ALVO DE GAP)
# -----------------------------------------------------------------------------
def resolver_flowshop_gurobi(dados, matriz_setup, c_atraso, c_estoque,
                             n_maq=4, time_limit=1800, mip_gap_alvo=0.05,
                             mostrar_progresso=True, verbose=False,
                             seq_inicial=None, usar_vnd_warmstart=True):
    """
    Resolve o Flowshop Permutacional via Gurobi acelerado com:
    1. Solução heurística refinada por VND (Swap + Inserção);
    2. MIP Start completo (variáveis x, C, w, T, E);
    3. Parada automática ao atingir mip_gap_alvo (padrão 5%) + barra de progresso.
    """
    log_gurobi = [
        f"\n=== RESOLUÇÃO EXATA VIA GUROBI (MILP + WARM START VND | "
        f"TimeLimit={time_limit}s | GapAlvo={mip_gap_alvo * 100:.1f}%) ==="
    ]
    ops = [x['op'] for x in dados]
    ops_dict = {x['op']: x for x in dados}
    n = len(ops)

    # 1. Gera e refina a solução heurística de partida
    if seq_inicial is None:
        seq_base, _ = construtiva_edd_setup(dados, matriz_setup, peso_setup=50.0)
    else:
        seq_base = seq_inicial.copy()

    custo_base = avaliar_sequencia(seq_base, dados, matriz_setup, c_atraso, c_estoque, n_maq)

    if usar_vnd_warmstart:
        seq_ws, custo_ws, iter_vnd, _ = vnd(
            seq_base, dados, matriz_setup, c_atraso, c_estoque,
            n_maq=n_maq, estruturas=['swap', 'insercao']
        )
        log_gurobi.append(
            f"Warm Start Heurístico : Base R$ {custo_base:.2f} -> Pós-VND R$ {custo_ws:.2f} "
            f"({iter_vnd} aval. VND)"
        )
    else:
        seq_ws = seq_base
        custo_ws = custo_base
        log_gurobi.append(f"Warm Start Heurístico : R$ {custo_ws:.2f}")

    # 2. Construção do Modelo Matemático
    model = gp.Model("Flowshop_Exact")
    model.Params.OutputFlag = 1 if verbose else 0
    model.Params.TimeLimit = time_limit
    model.Params.MIPGap = mip_gap_alvo    # Para assim que Gap <= 5%
    model.Params.MIPFocus = 1             # Foca em melhorar o limitante primal rapidamente
    model.Params.Cuts = 2                 # Cortes válidos agressivos
    model.Params.Cutoff = custo_ws + 1e-3

    max_setup = max(max(matriz_setup[f1][f2] for f2 in matriz_setup[f1]) for f1 in matriz_setup)
    soma_p = sum(sum(x['p']) for x in dados)
    horizonte = soma_p + (n - 1) * max_setup + max(x['d'] for x in dados)
    big_m = horizonte + max_setup + max(max(x['p']) for x in dados)

    def setup(i, j):
        return matriz_setup[ops_dict[i]['familia']][ops_dict[j]['familia']]

    x = {}
    for j in ops:
        x['START', j] = model.addVar(vtype=GRB.BINARY, name=f"x_START_{j}")
        for i in ops:
            if i != j:
                x[i, j] = model.addVar(vtype=GRB.BINARY, name=f"x_{i}_{j}")

    C = {(j, m): model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=horizonte, name=f"C_{j}_{m}")
         for j in ops for m in range(n_maq)}
    T = {j: model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, name=f"T_{j}") for j in ops}
    E = {j: model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, name=f"E_{j}") for j in ops}
    w = {(j, m): model.addVar(vtype=GRB.BINARY, name=f"w_{j}_{m}")
         for j in ops for m in range(1, n_maq)}

    model.setObjective(
        gp.quicksum(c_atraso * T[j] + c_estoque * E[j] for j in ops),
        sense=GRB.MINIMIZE
    )

    # (1) sequenciamento
    for j in ops:
        model.addConstr(x['START', j] + gp.quicksum(x[i, j] for i in ops if i != j) == 1)
    model.addConstr(gp.quicksum(x['START', j] for j in ops) == 1)
    for i in ops:
        model.addConstr(gp.quicksum(x[i, j] for j in ops if j != i) <= 1)

    # (2) fluxo
    for j in ops:
        model.addConstr(C[j, 0] >= ops_dict[j]['p'][0])
        for m in range(1, n_maq):
            model.addConstr(C[j, m] >= C[j, m - 1] + ops_dict[j]['p'][m])

    # (3) setup
    for i in ops:
        for j in ops:
            if i == j:
                continue
            s_ij = setup(i, j)
            for m in range(n_maq):
                model.addConstr(
                    C[j, m] >= C[i, m] + s_ij + ops_dict[j]['p'][m]
                    - big_m * (1 - x[i, j])
                )

    # (3b) semiativa
    for j in ops:
        p_j0 = ops_dict[j]['p'][0]
        model.addConstr(C[j, 0] <= p_j0 + big_m * (1 - x['START', j]))
        for i in ops:
            if i != j:
                model.addConstr(
                    C[j, 0] <= C[i, 0] + setup(i, j) + p_j0
                    + big_m * (1 - x[i, j])
                )
        for m in range(1, n_maq):
            p_jm = ops_dict[j]['p'][m]
            model.addConstr(w[j, m] >= x['START', j])
            model.addConstr(C[j, m] <= C[j, m - 1] + p_jm + big_m * (1 - w[j, m]))
            for i in ops:
                if i != j:
                    model.addConstr(
                        C[j, m] <= C[i, m] + setup(i, j) + p_jm
                        + big_m * (1 - x[i, j] + w[j, m])
                    )

    # (4) atraso / antecipação
    for j in ops:
        d_j = ops_dict[j]['d']
        model.addConstr(T[j] >= C[j, n_maq - 1] - d_j)
        model.addConstr(E[j] >= d_j - C[j, n_maq - 1])

    # 3. Injeção do MIP Start Completo (x, C, w, T, E)
    _, C_ws = _calcular_cronograma(seq_ws, dados, matriz_setup, n_maq)
    usados = {('START', seq_ws[0])} | {(seq_ws[k], seq_ws[k + 1]) for k in range(n - 1)}
    for key, var in x.items():
        var.Start = 1.0 if key in usados else 0.0

    for k, j in enumerate(seq_ws):
        for m in range(n_maq):
            C[j, m].Start = C_ws[k][m]
            if m >= 1:
                if k == 0:
                    w[j, m].Start = 1.0
                else:
                    s_prev = setup(seq_ws[k - 1], j)
                    w[j, m].Start = 1.0 if C_ws[k][m - 1] >= C_ws[k - 1][m] + s_prev - 1e-7 else 0.0

        d_j = ops_dict[j]['d']
        T[j].Start = max(0.0, C_ws[k][n_maq - 1] - d_j)
        E[j].Start = max(0.0, d_j - C_ws[k][n_maq - 1])

    # 4. Callback de Barra de Progresso em Tempo Real
    estado_prog = {
        'ultimo_print': 0.0,
        'gap_inicial': None,
        'spinner_idx': 0,
        'melhor_ub': custo_ws,
        'melhor_lb': 0.0,
        'nos': 0,
    }
    spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    def _renderizar_barra(ub, lb, nos, tempo_decorrido, finalizado=False):
        if ub <= 1e-9:
            gap_atual = 0.0
        else:
            gap_atual = max(0.0, (ub - lb) / ub)

        if lb > 1e-6 and estado_prog['gap_inicial'] is None:
            estado_prog['gap_inicial'] = max(gap_atual, mip_gap_alvo + 1e-4)

        if finalizado or gap_atual <= mip_gap_alvo + 1e-6:
            progresso = 1.0 if gap_atual <= mip_gap_alvo + 1e-6 else 0.0
            if not finalizado:
                progresso = 1.0
        elif estado_prog['gap_inicial'] is None:
            progresso = 0.0
        else:
            g0 = estado_prog['gap_inicial']
            progresso = min(1.0, max(0.0, (g0 - gap_atual) / (g0 - mip_gap_alvo)))

        largura_barra = 24
        preenchido = int(largura_barra * progresso)
        barra = '█' * preenchido + '░' * (largura_barra - preenchido)
        spin = '✔' if finalizado else spinners[estado_prog['spinner_idx'] % len(spinners)]
        estado_prog['spinner_idx'] += 1

        linha = (
            f"\r{spin} [{barra}] {progresso * 100:5.1f}% | "
            f"Gap: {gap_atual * 100:5.2f}% (Alvo: {mip_gap_alvo * 100:.1f}%) | "
            f"Melhor: R$ {ub:,.2f} | Bound: R$ {lb:,.2f} | "
            f"Nós: {int(nos)} | {tempo_decorrido:5.1f}s/{time_limit}s   "
        )
        sys.stdout.write(linha)
        sys.stdout.flush()

    def callback_progresso(cb_model, where):
        novo_incumbente = False
        if where == GRB.Callback.MIPSOL:
            obj_sol = cb_model.cbGet(GRB.Callback.MIPSOL_OBJ)
            obj_bnd = max(0.0, cb_model.cbGet(GRB.Callback.MIPSOL_OBJBND))
            nos = cb_model.cbGet(GRB.Callback.MIPSOL_NODCNT)
            if obj_sol < estado_prog['melhor_ub']:
                estado_prog['melhor_ub'] = obj_sol
                novo_incumbente = True
            estado_prog['melhor_lb'] = max(estado_prog['melhor_lb'], obj_bnd)
            estado_prog['nos'] = nos
        elif where == GRB.Callback.MIP:
            obj_bst = cb_model.cbGet(GRB.Callback.MIP_OBJBST)
            obj_bnd = max(0.0, cb_model.cbGet(GRB.Callback.MIP_OBJBND))
            nos = cb_model.cbGet(GRB.Callback.MIP_NODCNT)
            if obj_bst < estado_prog['melhor_ub']:
                estado_prog['melhor_ub'] = obj_bst
            estado_prog['melhor_lb'] = max(estado_prog['melhor_lb'], obj_bnd)
            estado_prog['nos'] = nos
        else:
            return

        agora = time.perf_counter()
        if novo_incumbente or (agora - estado_prog['ultimo_print']) >= 0.25:
            estado_prog['ultimo_print'] = agora
            runtime = cb_model.cbGet(GRB.Callback.RUNTIME)
            _renderizar_barra(
                estado_prog['melhor_ub'],
                estado_prog['melhor_lb'],
                estado_prog['nos'],
                runtime,
                finalizado=False
            )

    if mostrar_progresso and not verbose:
        print(f"\nOtimizando no Gurobi (Meta: Gap <= {mip_gap_alvo * 100:.1f}% | Limite: {time_limit}s)...")
        _renderizar_barra(custo_ws, 0.0, 0, 0.0, finalizado=False)
        model.optimize(callback_progresso)
    else:
        model.optimize()

    # 5. Reconstrução da sequência ótima
    seq_opt = []
    if model.SolCount > 0:
        curr = 'START'
        while len(seq_opt) < n:
            sucessor = None
            for j in ops:
                if curr != j and (curr, j) in x and x[curr, j].X > 0.5:
                    sucessor = j
                    break
            if sucessor is None:
                break
            seq_opt.append(sucessor)
            curr = sucessor
        if len(seq_opt) < n:
            faltando = [o for o in ops if o not in seq_opt]
            faltando.sort(key=lambda o: ops_dict[o]['d'])
            seq_opt.extend(faltando)
    else:
        seq_opt = seq_ws.copy()

    custo_avaliado = avaliar_sequencia(seq_opt, dados, matriz_setup, c_atraso, c_estoque, n_maq)
    bound_final = max(0.0, model.ObjBound) if hasattr(model, 'ObjBound') else estado_prog['melhor_lb']
    nos_finais = int(model.NodeCount) if hasattr(model, 'NodeCount') else estado_prog['nos']
    tempo_gurobi = model.Runtime if hasattr(model, 'Runtime') else 0.0

    if mostrar_progresso and not verbose:
        _renderizar_barra(custo_avaliado, bound_final, nos_finais, tempo_gurobi, finalizado=True)
        print()  # Quebra de linha ao concluir

    iteracoes_gurobi = int(model.IterCount) if hasattr(model, 'IterCount') else 0
    gap_final_pct = (model.MIPGap * 100.0) if model.SolCount > 0 else (
        max(0.0, (custo_avaliado - bound_final) / custo_avaliado) * 100.0 if custo_avaliado > 0 else 0.0
    )

    log_gurobi.append(f"Status Otimização : {model.status}")
    log_gurobi.append(f"Nós Explorados    : {nos_finais}")
    log_gurobi.append(f"Iterações Simplex : {iteracoes_gurobi}")
    log_gurobi.append(f"MIP Gap Alvo      : {mip_gap_alvo * 100:.2f}%")
    log_gurobi.append(f"MIP Gap Final     : {gap_final_pct:.2f}%")
    log_gurobi.append(f"Custo Final       : R$ {custo_avaliado:.2f}")

    return seq_opt, custo_avaliado, iteracoes_gurobi, log_gurobi
# -----------------------------------------------------------------------------
# DIAGRAMA DE GANTT (matplotlib)
# -----------------------------------------------------------------------------
CORES_FAMILIA = {"F1": "#4C78A8", "F2": "#F58518", "F3": "#54A24B"}
COR_SETUP = "#D62728"


def _calcular_cronograma(seq, dados, matriz_setup, n_maq=4):
    """Calcula as matrizes S (início) e C (término) por POSIÇÃO e máquina."""
    ops_dict = {x['op']: x for x in dados}
    n = len(seq)

    S = [[0.0] * n_maq for _ in range(n)]
    C = [[0.0] * n_maq for _ in range(n)]

    for k in range(n):
        op = seq[k]
        d = ops_dict[op]
        p = d['p']

        if k == 0:
            S[0][0] = 0.0
            C[0][0] = p[0]
            for m in range(1, n_maq):
                S[0][m] = C[0][m - 1]
                C[0][m] = S[0][m] + p[m]
        else:
            fam_prev = ops_dict[seq[k - 1]]['familia']
            fam_curr = d['familia']
            s = matriz_setup[fam_prev][fam_curr]

            S[k][0] = C[k - 1][0] + s
            C[k][0] = S[k][0] + p[0]
            for m in range(1, n_maq):
                S[k][m] = max(C[k][m - 1], C[k - 1][m] + s)
                C[k][m] = S[k][m] + p[m]

    return S, C


def gerar_grafico_gantt(seq, dados, matriz_setup, titulo_cenario, nome_arquivo_saida,
                        c_atraso=600.0, c_estoque=180.0, n_maq=4):
    """Desenha e salva o Gantt. Cria automaticamente a pasta de destino caso não exista."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    pasta_destino = os.path.dirname(nome_arquivo_saida)
    if pasta_destino:
        os.makedirs(pasta_destino, exist_ok=True)

    S, C = _calcular_cronograma(seq, dados, matriz_setup, n_maq)
    ops_dict = {x['op']: x for x in dados}
    custo = avaliar_sequencia(seq, dados, matriz_setup, c_atraso, c_estoque, n_maq)
    makespan = max(C[k][n_maq - 1] for k in range(len(seq)))

    fig, ax = plt.subplots(figsize=(14, 5))

    for m in range(n_maq):
        y = n_maq - 1 - m  # M1 no topo
        for k in range(len(seq)):
            op = seq[k]
            fam = ops_dict[op]['familia']
            p = ops_dict[op]['p'][m]

            ax.barh(y, p, left=S[k][m], height=0.6,
                    color=CORES_FAMILIA.get(fam, "gray"),
                    edgecolor="black", linewidth=0.6, zorder=3)
            if p >= makespan / 80:
                ax.text(S[k][m] + p / 2, y, op.replace("OP", ""),
                        ha="center", va="center", fontsize=7,
                        color="white", fontweight="bold", zorder=4)

            if k > 0:
                fam_prev = ops_dict[seq[k - 1]]['familia']
                setup_time = matriz_setup[fam_prev][fam]
                if setup_time > 0:
                    ax.barh(y, setup_time, left=C[k - 1][m], height=0.6,
                            facecolor="#F4B6B6", edgecolor=COR_SETUP, hatch="///",
                            linewidth=0.8, zorder=2)

    y4 = 0
    for op in seq:
        ax.plot(ops_dict[op]['d'], y4 - 0.42, marker="v", markersize=6,
                color=CORES_FAMILIA.get(ops_dict[op]['familia'], "gray"),
                markeredgecolor="black", markeredgewidth=0.6, zorder=5, clip_on=False)

    ax.set_yticks(range(n_maq))
    ax.set_yticklabels([f"M{n_maq - i}" for i in range(n_maq)])
    ax.set_ylim(-0.7, n_maq - 0.4)
    ax.set_xlim(0, max(makespan, max(o['d'] for o in dados)) * 1.03)
    ax.set_xlabel("Tempo (h)")
    ax.grid(axis="x", linestyle=":", alpha=0.5, zorder=0)

    fams_usadas = sorted(set(ops_dict[o]['familia'] for o in seq))
    handles = [Patch(facecolor=CORES_FAMILIA[f], edgecolor="black", label=f)
               for f in fams_usadas]
    handles.append(Patch(facecolor="#F4B6B6", edgecolor=COR_SETUP, hatch="///",
                         label="Setup / limpeza"))
    handles.append(Line2D([0], [0], marker="v", color="w",
                          markerfacecolor="lightgray", markeredgecolor="black",
                          markersize=7, label="Data de entrega $d_j$"))
    ax.legend(handles=handles, loc="upper center",
              bbox_to_anchor=(0.5, -0.12), ncol=len(handles), fontsize=9)

    ax.set_title(
        f"{titulo_cenario}\n"
        f"Custo = R$ {custo:,.2f}  |  Makespan = {makespan:.2f} h"
    )

    fig.tight_layout()
    fig.savefig(nome_arquivo_saida, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return nome_arquivo_saida