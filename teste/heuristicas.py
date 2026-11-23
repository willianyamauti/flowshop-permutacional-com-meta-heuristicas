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

_CACHE_INSTANCIAS = {}


def _compilar_instancia(dados, matriz_setup, n_maq):
    """Pré-compila estruturas numéricas para avaliação rápida de sequências."""
    chave = (
        id(dados),
        len(dados),
        n_maq,
        tuple((f1, tuple(sorted(matriz_setup[f1].items()))) for f1 in sorted(matriz_setup.keys())),
    )
    if chave in _CACHE_INSTANCIAS:
        return _CACHE_INSTANCIAS[chave]

    ops = [x['op'] for x in dados]
    op_to_idx = {op: i for i, op in enumerate(ops)}
    fams_unicas = sorted(set(x['familia'] for x in dados) | set(matriz_setup.keys()))
    fam_to_idx = {f: i for i, f in enumerate(fams_unicas)}

    p_list = [tuple(float(v) for v in x['p']) for x in dados]
    fam_list = [fam_to_idx[x['familia']] for x in dados]
    d_list = [float(x['d']) for x in dados]
    s_mat = [
        [float(matriz_setup[f1][f2]) for f2 in fams_unicas]
        for f1 in fams_unicas
    ]

    compilado = {
        'ops': ops,
        'op_to_idx': op_to_idx,
        'p_list': p_list,
        'fam_list': fam_list,
        'd_list': d_list,
        's_mat': s_mat,
    }
    _CACHE_INSTANCIAS[chave] = compilado
    return compilado


def _avaliar_indices(seq_idx, inst, c_atraso, c_estoque, n_maq):
    """Avalia uma permutação representada por índices inteiros."""
    p_list = inst['p_list']
    fam_list = inst['fam_list']
    d_list = inst['d_list']
    s_mat = inst['s_mat']

    c_prev = [0.0] * n_maq
    custo_total = 0.0

    for k, idx in enumerate(seq_idx):
        p_curr = p_list[idx]
        if k == 0:
            acc = 0.0
            for m in range(n_maq):
                acc += p_curr[m]
                c_prev[m] = acc
        else:
            s = s_mat[fam_list[seq_idx[k - 1]]][fam_list[idx]]
            c_prev[0] = c_prev[0] + s + p_curr[0]
            for m in range(1, n_maq):
                left = c_prev[m - 1]
                top = c_prev[m] + s
                c_prev[m] = (left if left > top else top) + p_curr[m]

        diff = c_prev[n_maq - 1] - d_list[idx]
        if diff > 0.0:
            custo_total += c_atraso * diff
        elif diff < 0.0:
            custo_total -= c_estoque * diff

    return custo_total


def avaliar_sequencia(seq, dados, matriz_setup, c_atraso, c_estoque, n_maq=4):
    """Simula o sequenciamento e calcula o Custo Total (Atraso + Estoque)."""
    if not seq:
        return 0.0
    inst = _compilar_instancia(dados, matriz_setup, n_maq)
    op_to_idx = inst['op_to_idx']
    seq_idx = [op_to_idx[op] for op in seq]
    return _avaliar_indices(seq_idx, inst, c_atraso, c_estoque, n_maq)


# -----------------------------------------------------------------------------
# ESTRATÉGIAS CONSTRUTIVAS
# -----------------------------------------------------------------------------
def construtiva_edd_setup(dados, matriz_setup, peso_setup=5.0):
    """
    Estratégia A: EDD ponderado pelo tempo de setup entre famílias.
    peso_setup=5.0 equilibra a economia de setup com a janela de entrega (d_j).
    """
    log = [f"=== CONSTRUÇÃO: ESTRATÉGIA A (EDD + SETUP | peso={peso_setup:.1f}) ==="]
    nao_agendados = dados.copy()
    seq = []

    nao_agendados.sort(key=lambda x: x['d'])
    primeira = nao_agendados.pop(0)
    seq.append(primeira['op'])
    fam_anterior = primeira['familia']
    log.append(
        f"Passo 1: Selecionada 1ª OP pelo menor Due Date: "
        f"{primeira['op']} (Família {fam_anterior}, d_j = {primeira['d']}h)"
    )

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
        log.append(
            f"Passo {passo}: Adicionada OP {melhor_cand['op']} "
            f"(Família {melhor_cand['familia']}, Score = {melhor_score:.2f})"
        )
        fam_anterior = melhor_cand['familia']
        nao_agendados.remove(melhor_cand)
        passo += 1

    return seq, log


def construtiva_parcialmente_gulosa(dados, matriz_setup, c_atraso, c_estoque, n_maq, alpha):
    """Estratégia B: Parcialmente Gulosa (RCL / GRASP) com avaliação incremental."""
    log = [f"=== CONSTRUÇÃO: ESTRATÉGIA B (PARCIALMENTE GULOSA - RCL alpha={alpha}) ==="]
    inst = _compilar_instancia(dados, matriz_setup, n_maq)
    ops = inst['ops']
    nao_agendados = list(range(len(ops)))
    seq_idx = []

    passo = 1
    while nao_agendados:
        custos_candidatos = []
        for cand_idx in nao_agendados:
            custo = _avaliar_indices(seq_idx + [cand_idx], inst, c_atraso, c_estoque, n_maq)
            custos_candidatos.append((cand_idx, custo))

        custos_candidatos.sort(key=lambda x: x[1])
        c_min = custos_candidatos[0][1]
        c_max = custos_candidatos[-1][1]
        limite = c_min + alpha * (c_max - c_min)
        rcl = [cand_idx for cand_idx, custo in custos_candidatos if custo <= limite]

        escolhido_idx = random.choice(rcl)
        seq_idx.append(escolhido_idx)
        nao_agendados.remove(escolhido_idx)
        log.append(
            f"Passo {passo}: C_min=R${c_min:.2f}, C_max=R${c_max:.2f}, "
            f"Limite RCL=R${limite:.2f} | Tamanho RCL={len(rcl)} | Escolhida: {ops[escolhido_idx]}"
        )
        passo += 1

    return [ops[i] for i in seq_idx], log


# -----------------------------------------------------------------------------
# ESTRUTURAS DE VIZINHANÇA (SWAP, INSERÇÃO E BLOCO DE FAMÍLIA)
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


def gerar_vizinhos_bloco(seq, tam_bloco=2):
    """Move blocos contíguos de tamanho `tam_bloco` preservando agrupamentos de família."""
    vizinhos = []
    n = len(seq)
    if n <= tam_bloco:
        return vizinhos
    for i in range(n - tam_bloco + 1):
        bloco = seq[i:i + tam_bloco]
        restante = seq[:i] + seq[i + tam_bloco:]
        for j in range(len(restante) + 1):
            if j == i:
                continue
            vizinho = restante[:j] + bloco + restante[j:]
            mov_desc = f"Bloco({'-'.join(bloco)}): pos {i} -> {j}"
            vizinhos.append((vizinho, mov_desc))
    return vizinhos


OBTER_VIZINHOS = {
    'swap': gerar_vizinhos_swap,
    'insercao': gerar_vizinhos_insercao,
    'bloco': gerar_vizinhos_bloco,
}


# -----------------------------------------------------------------------------
# BUSCA LOCAL & VND
# -----------------------------------------------------------------------------
def hill_climbing(seq_inicial, dados, matriz_setup, c_atraso, c_estoque,
                  n_maq=4, estrutura='insercao'):
    log_sub = []
    inst = _compilar_instancia(dados, matriz_setup, n_maq)
    op_to_idx = inst['op_to_idx']

    seq_atual = seq_inicial.copy()
    custo_atual = _avaliar_indices([op_to_idx[o] for o in seq_atual], inst, c_atraso, c_estoque, n_maq)

    func_vizinhos = OBTER_VIZINHOS[estrutura]
    melhorou = True
    iter_count = 0

    while melhorou:
        melhorou = False
        vizinhos = func_vizinhos(seq_atual)

        for vizinho, mov_desc in vizinhos:
            iter_count += 1
            custo_viz = _avaliar_indices([op_to_idx[o] for o in vizinho], inst, c_atraso, c_estoque, n_maq)

            if custo_viz < custo_atual - 1e-6:
                diff = custo_atual - custo_viz
                log_sub.append(
                    f"  [Iteração {iter_count}] MELHORA ENCONTRADA! {mov_desc} | "
                    f"Custo: R$ {custo_atual:.2f} -> R$ {custo_viz:.2f} (-R$ {diff:.2f})"
                )
                custo_atual = custo_viz
                seq_atual = vizinho
                melhorou = True
                break

    return seq_atual, custo_atual, iter_count, log_sub


def vnd(seq_inicial, dados, matriz_setup, c_atraso, c_estoque, n_maq=4, estruturas=None):
    if estruturas is None or len(estruturas) == 0:
        estruturas = ['insercao', 'swap', 'bloco']

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
            log_vnd.append(
                f"==> SUCESSO em N{k + 1} ({nome_viz.upper()}): Custo reduzido para "
                f"R$ {custo_linha:.2f} (-R$ {ganho:.2f}). Reiniciando para N1 ({estruturas[0].upper()}).\n"
            )
            seq_atual = seq_linha
            custo_atual = custo_linha
            k = 0
        else:
            log_vnd.append(
                f"==> SEM MELHORIAS em N{k + 1} ({nome_viz.upper()}). "
                f"Avançando para próxima vizinhança.\n"
            )
            k += 1

        passo_vnd += 1

    log_vnd.append("Fim do VND: Nenhuma vizinhança possui soluções melhores. Ótimo Local atingido!")
    return seq_atual, custo_atual, total_iteracoes, log_vnd


# -----------------------------------------------------------------------------
# META-HEURÍSTICA: GRASP (RCL + VND)
# -----------------------------------------------------------------------------
def grasp(dados, matriz_setup, c_atraso, c_estoque, n_maq=4,
          alpha=0.3, max_iter=100, estruturas=None, seq_inicial=None):
    """
    Greedy Randomized Adaptive Search Procedure (GRASP):
    Alterna construção aleatorizada gulosa (RCL) e busca local (VND).
    """
    if estruturas is None or len(estruturas) == 0:
        estruturas = ['insercao', 'swap', 'bloco']

    log_grasp = [
        f"\n=== META-HEURÍSTICA: GRASP (alpha={alpha}, max_iter={max_iter}, VND={estruturas}) ==="
    ]

    melhor_seq = None
    melhor_custo = float('inf')
    total_iteracoes = 0

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
                f"[Iteração {it:03d}/{max_iter}] NOVO MELHOR! RCL: R$ {custo_cand:.2f} -> "
                f"VND: R$ {custo_ref:.2f}" + (f" (-R$ {ganho:.2f})" if ganho > 0 else "")
            )
        elif it % 10 == 0 or it == max_iter:
            log_grasp.append(
                f"[Iteração {it:03d}/{max_iter}] RCL: R$ {custo_cand:.2f} -> "
                f"VND: R$ {custo_ref:.2f} (Melhor global: R$ {melhor_custo:.2f})"
            )

    log_grasp.append(f"\nFim do GRASP: Melhor custo encontrado = R$ {melhor_custo:.2f}")
    return melhor_seq, melhor_custo, total_iteracoes, log_grasp


# -----------------------------------------------------------------------------
# META-HEURÍSTICA: SIMULATED ANNEALING (SA AUTO-CALIBRADO)
# -----------------------------------------------------------------------------
def _gerar_vizinho_aleatorio_idx(seq_idx, estruturas):
    """Gera um vizinho aleatório diretamente sobre índices inteiros."""
    n = len(seq_idx)
    viz = seq_idx.copy()
    if n < 2:
        return viz, "Sem movimento"

    est = random.choice(estruturas)
    if est == 'bloco' and n >= 4:
        i = random.randint(0, n - 2)
        bloco = viz[i:i + 2]
        rest = viz[:i] + viz[i + 2:]
        j = random.randint(0, len(rest))
        viz = rest[:j] + bloco + rest[j:]
        return viz, f"Bloco ({i} -> {j})"

    i, j = random.sample(range(n), 2)
    if est == 'swap':
        viz[i], viz[j] = viz[j], viz[i]
        return viz, f"Swap ({i} <-> {j})"
    else:
        elem = viz.pop(i)
        viz.insert(j, elem)
        return viz, f"Inserção ({i} -> {j})"


def _calibrar_temperatura_inicial(seq_idx, custo_inicial, inst, c_atraso, c_estoque, n_maq, estruturas):
    """Estima T0 com base na magnitude real das variações de custo do cenário."""
    deltas_positivos = []
    for _ in range(30):
        viz, _ = _gerar_vizinho_aleatorio_idx(seq_idx, estruturas)
        cv = _avaliar_indices(viz, inst, c_atraso, c_estoque, n_maq)
        if cv > custo_inicial + 1e-6:
            deltas_positivos.append(cv - custo_inicial)

    if not deltas_positivos:
        return 2000.0
    media_delta = sum(deltas_positivos) / len(deltas_positivos)
    return max(500.0, -media_delta / math.log(0.45))


def simulated_annealing(seq_inicial, dados, matriz_setup, c_atraso, c_estoque,
                        n_maq=4, temp_inicial=None, temp_final=1.0,
                        taxa_resfriamento=0.95, iter_por_temp=50, estruturas=None):
    """
    Simulated Annealing (SA) auto-calibrado para Flowshop Permutacional com Setup.
    """
    if estruturas is None or len(estruturas) == 0:
        estruturas = ['insercao', 'swap', 'bloco']

    inst = _compilar_instancia(dados, matriz_setup, n_maq)
    ops = inst['ops']
    op_to_idx = inst['op_to_idx']

    seq_atual = [op_to_idx[o] for o in seq_inicial]
    custo_atual = _avaliar_indices(seq_atual, inst, c_atraso, c_estoque, n_maq)

    if temp_inicial is None:
        temp_inicial = _calibrar_temperatura_inicial(
            seq_atual, custo_atual, inst, c_atraso, c_estoque, n_maq, estruturas
        )
        temp_final = max(1.0, temp_inicial * 0.001)

    melhor_seq = seq_atual.copy()
    melhor_custo = custo_atual

    log_sa = [
        f"\n=== META-HEURÍSTICA: SIMULATED ANNEALING (T0={temp_inicial:.1f}, Tf={temp_final:.2f}, "
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
            vizinho, mov_desc = _gerar_vizinho_aleatorio_idx(seq_atual, estruturas)
            custo_viz = _avaliar_indices(vizinho, inst, c_atraso, c_estoque, n_maq)
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
    return [ops[i] for i in melhor_seq], melhor_custo, total_iteracoes, log_sa


# -----------------------------------------------------------------------------
# MÉTODO EXATO - GUROBI (WARM START VND + LIMITANTES FÍSICOS + BARRA DE PROGRESSO)
# -----------------------------------------------------------------------------
def resolver_flowshop_gurobi(dados, matriz_setup, c_atraso, c_estoque,
                             n_maq=4, time_limit=1800, mip_gap_alvo=0.05,
                             mostrar_progresso=True, verbose=False,
                             seq_inicial=None, usar_vnd_warmstart=True):
    """
    Resolve o Flowshop Permutacional via Gurobi acelerado com:
    1. Solução heurística refinada por VND (Inserção + Swap + Bloco);
    2. Limitantes físicos inferiores e superiores por máquina/operação (Big-M reduzido);
    3. MIP Start completo e parada automática ao atingir mip_gap_alvo (padrão 5%).
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
        seq_base, _ = construtiva_edd_setup(dados, matriz_setup, peso_setup=5.0)
    else:
        seq_base = seq_inicial.copy()

    custo_base = avaliar_sequencia(seq_base, dados, matriz_setup, c_atraso, c_estoque, n_maq)

    if usar_vnd_warmstart:
        seq_ws, custo_ws, iter_vnd, _ = vnd(
            seq_base, dados, matriz_setup, c_atraso, c_estoque,
            n_maq=n_maq, estruturas=['insercao', 'swap', 'bloco']
        )
        log_gurobi.append(
            f"Warm Start Heurístico : Base R$ {custo_base:.2f} -> Pós-VND R$ {custo_ws:.2f} "
            f"({iter_vnd} aval. VND)"
        )
    else:
        seq_ws = seq_base
        custo_ws = custo_base
        log_gurobi.append(f"Warm Start Heurístico : R$ {custo_ws:.2f}")

    # 2. Cálculo de Limitantes Físicos Estreitos
    max_setup = max(max(matriz_setup[f1][f2] for f2 in matriz_setup[f1]) for f1 in matriz_setup)
    soma_p = sum(sum(x['p']) for x in dados)
    horizonte_ativo = soma_p + (n - 1) * max_setup

    max_atraso_possivel = (custo_ws / c_atraso) if c_atraso > 0 else horizonte_ativo
    ub_c = {}
    lb_c = {}
    for j in ops:
        p_j = ops_dict[j]['p']
        d_j = ops_dict[j]['d']
        ub_ultima = min(horizonte_ativo, d_j + max_atraso_possivel)
        for m in range(n_maq):
            lb_c[j, m] = sum(p_j[:m + 1])
            cauda_p = sum(p_j[m + 1:])
            ub_c[j, m] = max(lb_c[j, m], min(horizonte_ativo, ub_ultima - cauda_p))

    # 3. Construção do Modelo Matemático
    model = gp.Model("Flowshop_Exact")
    model.Params.OutputFlag = 1 if verbose else 0
    model.Params.TimeLimit = time_limit
    model.Params.MIPGap = mip_gap_alvo
    model.Params.MIPFocus = 3
    model.Params.Cuts = 2
    model.Params.Presolve = 2
    model.Params.Cutoff = custo_ws + 1e-3

    def setup(i, j):
        return matriz_setup[ops_dict[i]['familia']][ops_dict[j]['familia']]

    x = {}
    for j in ops:
        x['START', j] = model.addVar(vtype=GRB.BINARY, name=f"x_START_{j}")
        for i in ops:
            if i != j:
                x[i, j] = model.addVar(vtype=GRB.BINARY, name=f"x_{i}_{j}")

    C = {
        (j, m): model.addVar(vtype=GRB.CONTINUOUS, lb=lb_c[j, m], ub=ub_c[j, m], name=f"C_{j}_{m}")
        for j in ops for m in range(n_maq)
    }
    T = {j: model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=max_atraso_possivel, name=f"T_{j}") for j in ops}
    E = {j: model.addVar(vtype=GRB.CONTINUOUS, lb=0.0, name=f"E_{j}") for j in ops}
    w = {
        (j, m): model.addVar(vtype=GRB.BINARY, name=f"w_{j}_{m}")
        for j in ops for m in range(1, n_maq)
    }

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
        for m in range(1, n_maq):
            model.addConstr(C[j, m] >= C[j, m - 1] + ops_dict[j]['p'][m])

    # (3) setup com Big-M estreito por par (i, j, m)
    for i in ops:
        for j in ops:
            if i == j:
                continue
            s_ij = setup(i, j)
            for m in range(n_maq):
                p_jm = ops_dict[j]['p'][m]
                m_ijm = max(0.0, ub_c[i, m] + s_ij + p_jm - lb_c[j, m])
                model.addConstr(
                    C[j, m] >= C[i, m] + s_ij + p_jm - m_ijm * (1 - x[i, j])
                )

    # (3b) semiativa com Big-M estreito
    for j in ops:
        p_j0 = ops_dict[j]['p'][0]
        m_start = max(0.0, ub_c[j, 0] - p_j0)
        model.addConstr(C[j, 0] <= p_j0 + m_start * (1 - x['START', j]))
        for i in ops:
            if i != j:
                m_0 = max(0.0, ub_c[j, 0] - lb_c[i, 0] - setup(i, j) - p_j0)
                model.addConstr(
                    C[j, 0] <= C[i, 0] + setup(i, j) + p_j0 + m_0 * (1 - x[i, j])
                )
        for m in range(1, n_maq):
            p_jm = ops_dict[j]['p'][m]
            model.addConstr(w[j, m] >= x['START', j])
            m_w1 = max(0.0, ub_c[j, m] - lb_c[j, m - 1] - p_jm)
            model.addConstr(C[j, m] <= C[j, m - 1] + p_jm + m_w1 * (1 - w[j, m]))
            for i in ops:
                if i != j:
                    m_w2 = max(0.0, ub_c[j, m] - lb_c[i, m] - setup(i, j) - p_jm)
                    model.addConstr(
                        C[j, m] <= C[i, m] + setup(i, j) + p_jm
                        + m_w2 * (1 - x[i, j] + w[j, m])
                    )

    # (4) atraso / antecipação
    for j in ops:
        d_j = ops_dict[j]['d']
        model.addConstr(T[j] >= C[j, n_maq - 1] - d_j)
        model.addConstr(E[j] >= d_j - C[j, n_maq - 1])

    # 4. Injeção do MIP Start Completo (x, C, w, T, E)
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

    # 5. Callback de Barra de Progresso em Tempo Real
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
        gap_atual = 0.0 if ub <= 1e-9 else max(0.0, (ub - lb) / ub)

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
                finalizado=False,
            )

    if mostrar_progresso and not verbose:
        print(f"\nOtimizando no Gurobi (Meta: Gap <= {mip_gap_alvo * 100:.1f}% | Limite: {time_limit}s)...")
        _renderizar_barra(custo_ws, 0.0, 0, 0.0, finalizado=False)
        model.optimize(callback_progresso)
    else:
        model.optimize()

    # 6. Reconstrução da sequência ótima
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
        print()

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
# MÉTODO EXATO COMBINATÓRIO - BRANCH-AND-BOUND PURO (SEM BIG-M)
# -----------------------------------------------------------------------------
def resolver_flowshop_bnb(dados, matriz_setup, c_atraso, c_estoque,
                          n_maq=4, time_limit=60, mostrar_progresso=True,
                          seq_inicial=None, usar_vnd_warmstart=True):
    """
    Resolve o Flowshop Permutacional via Branch-and-Bound combinatório exato
    (sem relaxação linear Big-M). Certifica Gap = 0.00% em instâncias pequenas/médias
    (ex: Cenários 1 e 2 em < 2s) e atua com time_limit nas maiores.
    """
    log_bnb = [
        f"\n=== RESOLUÇÃO EXATA VIA BRANCH-AND-BOUND COMBINATÓRIO (TimeLimit={time_limit}s) ==="
    ]
    inst = _compilar_instancia(dados, matriz_setup, n_maq)
    ops = inst['ops']
    op_to_idx = inst['op_to_idx']
    p_mat = inst['p_list']
    fam_list = inst['fam_list']
    d_vec = inst['d_list']
    s_mat = inst['s_mat']
    n = len(ops)

    # 1. Solução inicial + Warm Start VND
    if seq_inicial is None:
        seq_base, _ = construtiva_edd_setup(dados, matriz_setup, peso_setup=5.0)
    else:
        seq_base = seq_inicial.copy()

    custo_base = avaliar_sequencia(seq_base, dados, matriz_setup, c_atraso, c_estoque, n_maq)

    if usar_vnd_warmstart:
        seq_ws, custo_ws, iter_vnd, _ = vnd(
            seq_base, dados, matriz_setup, c_atraso, c_estoque,
            n_maq=n_maq, estruturas=['insercao', 'swap', 'bloco']
        )
        log_bnb.append(
            f"Warm Start Heurístico : Base R$ {custo_base:.2f} -> Pós-VND R$ {custo_ws:.2f} "
            f"({iter_vnd} aval. VND)"
        )
    else:
        seq_ws = seq_base
        custo_ws = custo_base
        log_bnb.append(f"Warm Start Heurístico : R$ {custo_ws:.2f}")

    # Ordena candidatos por Due Date crescente para poda mais rápida
    ordem_busca = sorted(range(n), key=lambda idx: d_vec[idx])
    all_mask = (1 << n) - 1

    estado = {
        'best_cost': custo_ws,
        'best_seq_idx': [op_to_idx[o] for o in seq_ws],
        'nodes': 0,
        'timed_out': False,
        'ultimo_print': 0.0,
        'spinner_idx': 0,
    }
    spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    t0 = time.perf_counter()

    def _print_status(finalizado=False):
        if not mostrar_progresso:
            return
        dt = time.perf_counter() - t0
        spin = '✔' if finalizado else spinners[estado['spinner_idx'] % len(spinners)]
        estado['spinner_idx'] += 1
        status_txt = (
            "Ótimo Comprovado (Gap 0.00%)"
            if (finalizado and not estado['timed_out'])
            else ("Limite de Tempo" if finalizado else "Buscando...")
        )
        sys.stdout.write(
            f"\r{spin} [B&B Exato] {status_txt} | "
            f"Melhor: R$ {estado['best_cost']:,.2f} | "
            f"Nós: {estado['nodes']:,} | {dt:5.2f}s/{time_limit}s   "
        )
        sys.stdout.flush()

    if mostrar_progresso:
        print(f"\nExecutando Branch-and-Bound Combinatório Exato (Limite: {time_limit}s)...")
        _print_status(False)

    if n_maq == 4:
        def dfs_4m(mask, prev_idx, c0, c1, c2, c3, acc_cost, cur_seq):
            estado['nodes'] += 1
            if (estado['nodes'] & 16383) == 0:
                agora = time.perf_counter()
                if agora - t0 >= time_limit:
                    estado['timed_out'] = True
                    return
                if agora - estado['ultimo_print'] >= 0.25:
                    estado['ultimo_print'] = agora
                    _print_status(False)

            if mask == all_mask:
                if acc_cost < estado['best_cost'] - 1e-6:
                    estado['best_cost'] = acc_cost
                    estado['best_seq_idx'] = cur_seq.copy()
                return

            # Limitante inferior admissível (atraso mínimo imediato + capacidade M4)
            lb_indiv = 0.0
            unsched = []
            unsched_p3 = []
            unsched_d = []
            for j in ordem_busca:
                if not (mask & (1 << j)):
                    unsched.append(j)
                    pj = p_mat[j]
                    dj = d_vec[j]
                    unsched_p3.append(pj[3])
                    unsched_d.append(dj)
                    if prev_idx == -1:
                        ec0 = pj[0]
                        ec1 = ec0 + pj[1]
                        ec2 = ec1 + pj[2]
                        ec3 = ec2 + pj[3]
                    else:
                        s = s_mat[fam_list[prev_idx]][fam_list[j]]
                        ec0 = c0 + s + pj[0]
                        ec1 = (ec0 if ec0 > c1 + s else c1 + s) + pj[1]
                        ec2 = (ec1 if ec1 > c2 + s else c2 + s) + pj[2]
                        ec3 = (ec2 if ec2 > c3 + s else c3 + s) + pj[3]
                    if ec3 > dj:
                        lb_indiv += c_atraso * (ec3 - dj)

            unsched_p3.sort()
            t_m4 = c3
            lb_cap = 0.0
            for pm4, dj in zip(unsched_p3, unsched_d):
                t_m4 += pm4
                if t_m4 > dj:
                    lb_cap += c_atraso * (t_m4 - dj)

            lb_extra = lb_indiv if lb_indiv > lb_cap else lb_cap
            if acc_cost + lb_extra >= estado['best_cost'] - 1e-6:
                return

            for j in unsched:
                if estado['timed_out']:
                    return
                pj = p_mat[j]
                if prev_idx == -1:
                    nc0 = pj[0]
                    nc1 = nc0 + pj[1]
                    nc2 = nc1 + pj[2]
                    nc3 = nc2 + pj[3]
                else:
                    s = s_mat[fam_list[prev_idx]][fam_list[j]]
                    nc0 = c0 + s + pj[0]
                    nc1 = (nc0 if nc0 > c1 + s else c1 + s) + pj[1]
                    nc2 = (nc1 if nc1 > c2 + s else c2 + s) + pj[2]
                    nc3 = (nc2 if nc2 > c3 + s else c3 + s) + pj[3]

                diff = nc3 - d_vec[j]
                step_cost = c_atraso * diff if diff > 0.0 else -c_estoque * diff
                if acc_cost + step_cost < estado['best_cost'] - 1e-6:
                    cur_seq.append(j)
                    dfs_4m(mask | (1 << j), j, nc0, nc1, nc2, nc3, acc_cost + step_cost, cur_seq)
                    cur_seq.pop()

        dfs_4m(0, -1, 0.0, 0.0, 0.0, 0.0, 0.0, [])
    else:
        def dfs_gen(mask, prev_idx, c_prev, acc_cost, cur_seq):
            estado['nodes'] += 1
            if (estado['nodes'] & 16383) == 0:
                if time.perf_counter() - t0 >= time_limit:
                    estado['timed_out'] = True
                    return
            if mask == all_mask:
                if acc_cost < estado['best_cost'] - 1e-6:
                    estado['best_cost'] = acc_cost
                    estado['best_seq_idx'] = cur_seq.copy()
                return
            for j in ordem_busca:
                if estado['timed_out']:
                    return
                if not (mask & (1 << j)):
                    pj = p_mat[j]
                    nc = [0.0] * n_maq
                    if prev_idx == -1:
                        nc[0] = pj[0]
                        for m in range(1, n_maq):
                            nc[m] = nc[m - 1] + pj[m]
                    else:
                        s = s_mat[fam_list[prev_idx]][fam_list[j]]
                        nc[0] = c_prev[0] + s + pj[0]
                        for m in range(1, n_maq):
                            top = c_prev[m] + s
                            nc[m] = (nc[m - 1] if nc[m - 1] > top else top) + pj[m]
                    diff = nc[n_maq - 1] - d_vec[j]
                    step_cost = c_atraso * diff if diff > 0.0 else -c_estoque * diff
                    if acc_cost + step_cost < estado['best_cost'] - 1e-6:
                        cur_seq.append(j)
                        dfs_gen(mask | (1 << j), j, nc, acc_cost + step_cost, cur_seq)
                        cur_seq.pop()

        dfs_gen(0, -1, [0.0] * n_maq, 0.0, [])

    _print_status(True)
    if mostrar_progresso:
        print()

    seq_opt = [ops[i] for i in estado['best_seq_idx']]
    custo_final = avaliar_sequencia(seq_opt, dados, matriz_setup, c_atraso, c_estoque, n_maq)
    status_str = (
        "LIMITE DE TEMPO ATINGIDO (Melhor Solução B&B)"
        if estado['timed_out']
        else "ÓTIMO GLOBAL COMPROVADO (Gap = 0.00%)"
    )

    log_bnb.append(f"Status Otimização : {status_str}")
    log_bnb.append(f"Nós Explorados    : {estado['nodes']}")
    log_bnb.append(f"MIP Gap Final     : {'N/A (Timeout)' if estado['timed_out'] else '0.00%'}")
    log_bnb.append(f"Custo Final       : R$ {custo_final:.2f}")

    return seq_opt, custo_final, estado['nodes'], log_bnb


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
