# Relatório Técnico: Otimização de Sequenciamento em Flowshop Permutacional com Setup Dependente de Família

---

## 1. Resumo Executivo

Este relatório apresenta a modelagem, os métodos de resolução e a análise experimental comparativa para o problema de sequenciamento de ordens de produção (OPs) em um ambiente **Flowshop Permutacional** com $4$ máquinas ($M_1, M_2, M_3, M_4$) e tempos de preparação (*setup*) dependentes da família do produto ($F_1, F_2, F_3$). O objetivo operacional consiste em minimizar o custo total combinado de **atrasos nas entregas** e **antecipações (estoque intermediário/acabado)**.

Foram avaliadas cinco abordagens distintas sobre cinco cenários de complexidade crescente (até $25$ OPs):
1. **Branch-and-Bound Combinatório Exato** (sem relaxação *Big-M*, inicializado com *Warm Start* VND);
2. **GRASP** (*Greedy Randomized Adaptive Search Procedure*) com fator de aleatoriedade $\alpha = 0,3$ e busca local VND;
3. **GRASP** com fator de aleatoriedade $\alpha = 0,7$ e busca local VND;
4. **Simulated Annealing (SA)** auto-calibrado partindo da heurística construtiva **EDD + Setup**;
5. **Simulated Annealing (SA)** auto-calibrado partindo da construtiva **Parcialmente Gulosa (RCL com $\alpha = 0,3$)**.

Com a extensão do limite de tempo do solver exato para $9.000\text{ s}$ ($2\text{h}30\text{min}$), o **Branch-and-Bound Combinatório atingiu o Ótimo Global Comprovado ($\text{Gap} = 0,00\%$) em 100% dos cinco cenários**, explorando $201.666.064$ nós em $2.143,91\text{ s}$ acumulados. A certificação exata confirmou que a meta-heurística **GRASP ($\alpha = 0,3$)** encontrou o **ótimo global real em todos os cinco cenários ($\text{RPD} = 0,00\%$)** em apenas **$75,83\text{ s}$ no total** — entregando uma velocidade **$28,3\times$ superior** à do método exato sem perda de qualidade.

---

## 2. Formulação do Problema e Parâmetros Operacionais

### 2.1 Estrutura Produtiva e Custos
No ambiente estudado, um conjunto de $n$ ordens de produção deve ser processado na mesma sequência permutacional $\pi = (\pi_1, \pi_2, \dots, \pi_n)$ através de $M = 4$ máquinas em série. Cada ordem $j$ pertence a uma família $f_j \in \{F_1, F_2, F_3\}$, possui tempos de processamento $p_{j,m}$ em cada máquina $m \in \{1, 2, 3, 4\}$ e uma data de entrega prometida $d_j$ (em horas).

A função objetivo minimiza a soma das penalidades de atraso ($T_j$) e de antecipação/estoque ($E_j$) medidas na conclusão da última máquina ($C_{\pi_k, 4}$):

$$\min Z(\pi) = \sum_{k=1}^{n} \left( c_{\text{atraso}} \cdot T_{\pi_k} + c_{\text{estoque}} \cdot E_{\pi_k} \right)$$

sujeita às relações de fluxo, setup e desvios de prazo:

$$T_{\pi_k} = \max\left(0,\; C_{\pi_k, 4} - d_{\pi_k}\right), \qquad E_{\pi_k} = \max\left(0,\; d_{\pi_k} - C_{\pi_k, 4}\right)$$

$$C_{\pi_k, m} = \max\left(C_{\pi_k, m-1},\; C_{\pi_{k-1}, m} + s(f_{\pi_{k-1}}, f_{\pi_k})\right) + p_{\pi_k, m}$$

onde os parâmetros financeiros do problema são:
* **Custo unitário de atraso:** $c_{\text{atraso}} = \text{R\$ } 600,00\text{ / hora}$;
* **Custo unitário de antecipação (estoque):** $c_{\text{estoque}} = \text{R\$ } 180,00\text{ / hora}$.

### 2.2 Matriz de Setup Dependente de Família
Sempre que duas ordens consecutivas pertencem a famílias distintas, incorre-se em um tempo de limpeza e preparação $s(f_{\text{anterior}}, f_{\text{atual}})$ (em horas) aplicado antes do início da operação nas máquinas:

| Família Anterior $\backslash$ Atual | $F_1$ | $F_2$ | $F_3$ |
| :--- | :---: | :---: | :---: |
| **$F_1$** | $0,0\text{ h}$ | $2,0\text{ h}$ | $3,0\text{ h}$ |
| **$F_2$** | $3,5\text{ h}$ | $0,0\text{ h}$ | $1,5\text{ h}$ |
| **$F_3$** | $4,0\text{ h}$ | $2,5\text{ h}$ | $0,0\text{ h}$ |

---

## 3. Metodologia de Resolução

### 3.1 Heurísticas Construtivas (Soluções Iniciais)
* **Estratégia A (EDD + Setup Ponderado):** Ordena a primeira OP pelo menor prazo de entrega ($d_j$) e seleciona iterativamente a próxima operação que minimiza o escore composto $\text{Score}(j) = d_j + w_s \cdot s(f_{\text{anterior}}, f_j)$, com peso $w_s = 5,0$, equilibrando urgência de entrega e agrupamento de famílias.
* **Estratégia B (Parcialmente Gulosa — RCL):** Avalia incrementalmente o custo parcial de inserir cada OP candidata ao final da sequência em construção. Define uma Lista Restrita de Candidatos (*Restricted Candidate List* — RCL) contendo as operações com custo até $C_{\min} + \alpha \cdot (C_{\max} - C_{\min})$ e sorteia uma candidata, introduzindo diversificação controlada pelo parâmetro $\alpha \in [0, 1]$.

### 3.2 Busca Local Multi-Vizinhança (VND)
O refinamento local utiliza o algoritmo **VND (*Variable Neighborhood Descent*)** com estratégia *first-improvement* sobre três estruturas de vizinhança complementares:
1. **Inserção ($N_1$):** Remove uma OP da posição $i$ e a reinsere na posição $j$ ($i \neq j$), ajustando diretamente sua janela de entrega $d_j$;
2. **Swap ($N_2$):** Troca diretamente as posições de duas OPs $i$ e $j$;
3. **Bloco ($N_3$):** Desloca blocos contíguos de duas OPs adjacentes $(\pi_i, \pi_{i+1})$ para outra posição da fila, preservando agrupamentos já formados de uma mesma família sem quebrar a economia de *setup*.

### 3.3 Meta-heurísticas Implementadas
* **GRASP (Multi-Start):** Executa $100$ iterações independentes alternando a construção aleatorizada via RCL ($\alpha = 0,3$ ou $\alpha = 0,7$) e a intensificação completa até o ótimo local pelo VND (`Inserção + Swap + Bloco`).
* **Simulated Annealing (SA Auto-Calibrado):** Parte de uma solução inicial (EDD ou RCL) e realiza movimentos aleatórios sorteados entre `Inserção`, `Swap` e `Bloco`. A temperatura inicial $T_0$ é calibrada automaticamente com base na média dos deltas positivos de custo ($\Delta > 0$) observados em $30$ perturbações iniciais, visando uma taxa inicial de aceitação de pioras de $45\%$, com resfriamento geométrico ($\text{taxa} = 0,95$ e $L = 50$ iterações por patamar).

### 3.4 Método Exato: Branch-and-Bound Combinatório
Em substituição a formulações lineares inteiras mistas (MILP) com constantes *Big-M* — que sofrem com relaxações lineares fracas e alta sobrecarga de matrizes simplex —, foi implementado um **Branch-and-Bound Combinatório** puro em profundidade:
* **Warm Start VND:** Inicia a busca com o limitante superior (*Upper Bound*) já refinado pelo VND a partir da solução EDD + Setup;
* **Ordenação de Ramificação:** Prioriza candidatos em ordem crescente de *Due Date* ($d_j$) para encontrar soluções de baixo custo rapidamente e acelerar as podas;
* **Podas por Limitantes Inferiores Admissíveis:** Descarta subárvores inteiras sempre que o custo acumulado somado ao limitante inferior do subproblema restante atinge ou supera o melhor custo incumbente.

---

## 4. Resultados Experimentais Consolidados

### 4.1 Panorama Geral e Certificação de Otimalidade
Com o limite de tempo configurado em $9.000\text{ s}$ por cenário, **todos os cinco cenários convergiram antes do limite de tempo**, obtendo o certificado matemático de **Ótimo Global Comprovado ($\text{Gap} = 0,00\%$)**. Para comparação entre algoritmos, utiliza-se o **RPD (*Relative Percentage Deviation*)**:

$$\text{RPD (\%)} = \frac{C_{\text{algoritmo}} - C_{\text{ótimo}}}{C_{\text{ótimo}}} \times 100$$

| Método / Configuração | Custo Médio Final | RPD Médio (%) | RPD Máximo (%) | Ótimos Globais Atingidos | Tempo Médio (s) | Tempo Total (s) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RCL ($\alpha=0,3$) + GRASP** | **R$ 31.356,00** | **0,00%** | **0,00%** | **5 / 5 (100%)** | $15,17$ | $75,83$ |
| **RCL ($\alpha=0,7$) + GRASP** | **R$ 31.356,00** | **0,00%** | **0,00%** | **5 / 5 (100%)** | $29,78$ | $148,88$ |
| **EDD + Branch-and-Bound Exato** | **R$ 31.356,00** | **0,00%** | **0,00%** | **5 / 5 (100%)** | $428,78$ | $2.143,91$ |
| **EDD + Simulated Annealing** | R$ 32.130,00 | $1,87\%$ | $7,46\%$ | 3 / 5 (60%) | **$0,14$** | **$0,72$** |
| **RCL ($\alpha=0,3$) + Simulated Annealing** | R$ 33.384,00 | $4,79\%$ | $13,52\%$ | 2 / 5 (40%) | $0,15$ | $0,74$ |

### 4.2 Cenários 1 e 2 (Instâncias de Pequeno e Médio Porte)
Nos **Cenários 1 e 2**, o Branch-and-Bound Combinatório certificou o ótimo global ($\text{Gap} = 0,00\%$) de forma praticamente instantânea:
* **Cenário 1:** Ótimo global comprovado em **$0,0133\text{ s}$**;
* **Cenário 2:** Ótimo global comprovado em **$0,9050\text{ s}$**;
* **Consolidado (Cenários 1 e 2):** Exploraram conjuntamente $117.110$ nós em $0,92\text{ s}$, somando custo ótimo combinado de **R$ 28.710,00**. Todas as variantes de GRASP e Simulated Annealing também atingiram o ótimo global ($\text{RPD} = 0,00\%$) nesses dois cenários.

### 4.3 Cenário 3 ($15$ Ordens de Produção)
No Cenário 3, o Branch-and-Bound explorou **$111.037.962$ nós** em **$1.029,23\text{ s}$** ($\approx 17\text{ min } 09\text{ s}$), reduzindo o custo do *Warm Start* VND (R$ 43.110,00) até o **ótimo global de R$ 42.570,00 ($\text{Gap} = 0,00\%$)**. O GRASP ($\alpha = 0,3$) encontrou essa mesma sequência ótima logo na $8^{\text{a}}$ iteração, em apenas **$3,60\text{ s}$**.

| Configuração (Cenário 3) | Custo Inicial | Custo Final | Redução (%) | RPD (%) | Tempo (s) | Nós / Avaliações |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **EDD + Branch-and-Bound Exato** | R$ 86.490,00 | **R$ 42.570,00** | $50,78\%$ | **0,00%** | $1.029,2340$ | $111.037.962$ |
| **RCL ($\alpha=0,3$) + GRASP** | R$ 65.700,00 | **R$ 42.570,00** | $35,21\%$ | **0,00%** | $3,6006$ | $214.930$ |
| **RCL ($\alpha=0,7$) + GRASP** | R$ 93.330,00 | **R$ 42.570,00** | $54,39\%$ | **0,00%** | $5,4277$ | $301.414$ |
| **EDD + Simulated Annealing** | R$ 86.490,00 | R$ 43.380,00 | $49,84\%$ | $1,90\%$ | $0,1342$ | $6.750$ |
| **RCL ($\alpha=0,3$) + Simulated Annealing** | R$ 53.730,00 | R$ 43.470,00 | $19,10\%$ | $2,11\%$ | $0,1371$ | $6.750$ |

* **Sequência Ótima Global (Cenário 3):** `OP08 -> OP13 -> OP03 -> OP07 -> OP09 -> OP01 -> OP05 -> OP04 -> OP12 -> OP02 -> OP10 -> OP15 -> OP11 -> OP06 -> OP14`.

### 4.4 Cenário 4 ($25$ Ordens de Produção)
Embora possua o maior número de operações ($n = 25$), a estrutura de prazos e famílias do Cenário 4 favoreceu uma poda extremamente agressiva: o Branch-and-Bound certificou o **ótimo global de R$ 41.040,00 ($\text{Gap} = 0,00\%$)** explorando apenas **$2.724.863$ nós** em **$69,09\text{ s}$**. O GRASP ($\alpha = 0,3$) atingiu o mesmo ótimo global na $5^{\text{a}}$ iteração em **$45,20\text{ s}$**, enquanto o Simulated Annealing ficou retido em mínimos locais com custos $7,46\%$ a $13,52\%$ acima do ótimo.

| Configuração (Cenário 4) | Custo Inicial | Custo Final | Redução (%) | RPD (%) | Tempo (s) | Nós / Avaliações |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **EDD + Branch-and-Bound Exato** | R$ 151.110,00 | **R$ 41.040,00** | $72,84\%$ | **0,00%** | $69,0866$ | $2.724.863$ |
| **RCL ($\alpha=0,3$) + GRASP** | R$ 101.640,00 | **R$ 41.040,00** | $59,62\%$ | **0,00%** | $45,2028$ | $1.715.022$ |
| **RCL ($\alpha=0,7$) + GRASP** | R$ 216.180,00 | **R$ 41.040,00** | $81,02\%$ | **0,00%** | $106,3848$ | $3.931.771$ |
| **EDD + Simulated Annealing** | R$ 151.110,00 | R$ 44.100,00 | $70,82\%$ | $7,46\%$ | $0,1937$ | $6.750$ |
| **RCL ($\alpha=0,3$) + Simulated Annealing** | R$ 91.620,00 | R$ 46.590,00 | $49,15\%$ | $13,52\%$ | $0,2142$ | $6.750$ |

* **Sequência Ótima Global (Cenário 4):** `OP02 -> OP01 -> OP12 -> OP04 -> OP03 -> OP05 -> OP07 -> OP09 -> OP13 -> OP06 -> OP10 -> OP08 -> OP11 -> OP16 -> OP14 -> OP19 -> OP15 -> OP20 -> OP17 -> OP22 -> OP18 -> OP23 -> OP21 -> OP25 -> OP24`.

### 4.5 Cenário 5 ($20$ Ordens de Produção)
No Cenário 5, devido ao maior acoplamento e conflito entre datas de entrega, o Branch-and-Bound explorou **$87.786.129$ nós** em **$1.044,67\text{ s}$** ($\approx 17\text{ min } 25\text{ s}$), comprovando que o custo de **R$ 44.460,00** já alcançado pelo *Warm Start* VND é o **ótimo global ($\text{Gap} = 0,00\%$)**. Tanto o GRASP ($\alpha = 0,3$ na iteração $1$ e $\alpha = 0,7$ na iteração $2$) quanto o EDD + Simulated Annealing convergiram para a exata mesma sequência ótima global.

| Configuração (Cenário 5) | Custo Inicial | Custo Final | Redução (%) | RPD (%) | Tempo (s) | Nós / Avaliações |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **EDD + Branch-and-Bound Exato** | R$ 111.960,00 | **R$ 44.460,00** | $60,29\%$ | **0,00%** | $1.044,6748$ | $87.786.129$ |
| **EDD + Simulated Annealing** | R$ 111.960,00 | **R$ 44.460,00** | $60,29\%$ | **0,00%** | $0,1623$ | $6.750$ |
| **RCL ($\alpha=0,3$) + GRASP** | R$ 76.830,00 | **R$ 44.460,00** | $42,13\%$ | **0,00%** | $24,0751$ | $1.119.220$ |
| **RCL ($\alpha=0,7$) + GRASP** | R$ 223.470,00 | **R$ 44.460,00** | $80,10\%$ | **0,00%** | $33,9998$ | $1.509.627$ |
| **RCL ($\alpha=0,3$) + Simulated Annealing** | R$ 88.470,00 | R$ 48.150,00 | $45,57\%$ | $8,30\%$ | $0,1750$ | $6.750$ |

* **Sequência Ótima Global (Cenário 5):** `OP01 -> OP09 -> OP07 -> OP03 -> OP04 -> OP06 -> OP16 -> OP12 -> OP13 -> OP15 -> OP10 -> OP02 -> OP18 -> OP11 -> OP19 -> OP05 -> OP08 -> OP14 -> OP17 -> OP20`.

---

## 5. Análise de Confiabilidade e Eficiência Computacional

Uma questão central em problemas de otimização combinatória NP-difíceis — nos quais o espaço de busca cresce fatorialmente ($15! \approx 1,31 \times 10^{12}$, $20! \approx 2,43 \times 10^{18}$ e $25! \approx 1,55 \times 10^{25}$ permutações) — é compreender **por que as soluções obtidas são matematicamente e estatisticamente confiáveis mesmo sendo encontradas em tempos relativamente curtos** (entre dezenas de segundos e poucos minutos). Essa confiabilidade decorre de cinco pilares estruturais implementados na arquitetura do solver.

### 5.1 Garantias Matemáticas do Branch-and-Bound Combinatório

1. **Enumeração Implícita Completa com Certificado ($\text{Gap} = 0,00\%$):**
   O baixo tempo de execução não significa que o espaço de soluções foi truncado ou amostrado parcialmente. Quando o Branch-and-Bound finaliza sem atingir o *timeout*, **todas** as $n!$ permutações possíveis foram ou explicitamente avaliadas ou matematicamente dominadas. A indicação $\text{Gap} = 0,00\%$ constitui uma **prova determinística** de que nenhuma sequência no universo combinatório da instância possui custo estritamente inferior ao reportado.

2. **Eliminação da Formulação MILP com Constantes Big-M:**
   Modelos clássicos de Programação Linear Inteira Mista (MILP) para Flowshop com setup utilizam variáveis binárias de precedência e restrições disjuntivas com constantes $M_{ijm}$. Esse modelo sofre com relaxações lineares muito frouxas (limitantes inferiores próximos de zero) e alto custo computacional por nó devido à resolução de subproblemas Simplex. Ao substituir o MILP por um **Branch-and-Bound Combinatório puro**, cada nó da árvore calcula o cronograma exato diretamente por recorrência de programação dinâmica em tempo $O(M)$ ($M = 4$ máquinas), eliminando o *overhead* matricial.

3. **Limitantes Inferiores Admissíveis (*Lower Bounds* Conservadores):**
   Em cada estado parcial da árvore de busca, o algoritmo calcula dois limitantes inferiores que **nunca superestimam** o custo real das operações ainda não alocadas ($\mathcal{U}$):
   * **Limitante Individual de Atraso ($LB_{\text{indiv}}$):** Calcula o instante mais cedo possível de término na máquina gargalo ($EC_{j,4}$) para cada OP $j \in \mathcal{U}$ considerando apenas o estado atual das máquinas e o setup direto, acumulando a penalidade mínima inevitável:
     $$LB_{\text{indiv}} = \sum_{j \in \mathcal{U}} c_{\text{atraso}} \cdot \max\left(0,\; EC_{j,4} - d_j\right)$$
   * **Limitante de Capacidade da Última Máquina ($LB_{\text{cap}}$):** Ordena os tempos de processamento restantes na máquina $M_4$ em ordem crescente e simula a fila mínima contínua a partir de $C_{\text{atual}, 4}$ (assumindo setup nulo e disponibilidade imediata), confrontando os términos com os prazos ordenados $d_j$.

   Adota-se $LB_{\text{extra}} = \max(LB_{\text{indiv}}, LB_{\text{cap}})$. Como ambos são limitantes inferiores válidos (relaxações conservadoras), sempre que:
   $$\text{Custo Acumulado} + LB_{\text{extra}} \ge \text{Melhor Custo Incumbente}$$
   o algoritmo descarta com **100% de certeza matemática** toda a subárvore descendente, pois nenhuma completude daquela sequência parcial poderá superar a melhor solução já conhecida. No Cenário 4 ($25! \approx 1,55 \times 10^{25}$ sequências), esse mecanismo reduziu a busca efetiva a apenas $2.724.863$ nós ($69,09\text{ s}$).

4. **Impacto do *Warm Start* VND e Ordenação por *Due Date*:**
   A eficiência da poda depende diretamente da qualidade do limitante superior (*Upper Bound*) inicial. Ao iniciar com a heurística **EDD + Setup** refinada pelo **VND** (que reduz o custo inicial em até $70\%$ antes mesmo da abertura do primeiro nó da árvore) e ordenar os candidatos por $d_j$ crescente, o solver estabelece um teto apertado desde o milissegundo inicial, podando ramos subótimos ainda nos primeiros níveis da árvore.

5. **Otimização Computacional de Baixo Nível:**
   A implementação utiliza representação de conjuntos via máscaras de bits inteiras (`mask | (1 << j)`), pré-compilação de instâncias em vetores numéricos contíguos (`_compilar_instancia`) e desenrolamento de laços específico para $4$ máquinas (`dfs_4m`), atingindo taxas superiores a **$84.000$ a $108.000$ nós explorados por segundo** em memória.

### 5.2 Confiabilidade da Meta-heurística GRASP em Segundos

1. **Validação Cruzada Exata contra o Ótimo Global:**
   Em meta-heurísticas, a confiabilidade costuma ser medida apenas de forma relativa. Neste trabalho, a existência do certificado exato nos cinco cenários permitiu comprovar empiricamente que o **GRASP ($\alpha = 0,3$)** atingiu o **ótimo global real em 5 de 5 cenários ($\text{RPD} = 0,00\%$)**, incluindo instâncias de $15$, $20$ e $25$ OPs.

2. **Sinergia entre Diversificação (RCL) e Intensificação Multi-Vizinhança (VND):**
   A velocidade do GRASP não decorre de uma busca superficial, mas da complementaridade entre suas duas fases:
   * A **RCL ($\alpha = 0,3$)** constrói $100$ pontos de partida distintos guiados pelo custo incremental real, evitando regiões inviáveis sem ficar presa a um único caminho guloso;
   * O **VND** aplica busca local exaustiva em três vizinhanças (`Inserção`, `Swap` e `Bloco`). O operador de **`Bloco`** desempenha papel decisivo ao movimentar pares adjacentes de OPs simultaneamente, permitindo realocar grupos inteiros de uma mesma família ($F_1, F_2$ ou $F_3$) sem destruir a economia de *setup* já conquistada.

3. **Estabilidade Estatística Frente ao Simulated Annealing:**
   Enquanto o Simulated Annealing em rodada única ($\approx 0,15\text{ s}$) mostrou sensibilidade à solução inicial e estagnou em mínimos locais nos Cenários 3, 4 e 5 ($\text{RPD}$ de até $13,52\%$), o caráter *multi-start* do GRASP ($100$ reinícios independentes com busca local completa) garantiu **variância nula no resultado final** entre $\alpha = 0,3$ e $\alpha = 0,7$, encontrando o ótimo global logo nas primeiras iterações (iterações $8$, $5$ e $1$ nos Cenários 3, 4 e 5, respectivamente) e utilizando as demais iterações como margem de segurança estatística.

---

## 6. Conclusões e Recomendações Operacionais

1. **Validar a Otimalidade das Soluções:** A bateria estendida do Branch-and-Bound Combinatório eliminou qualquer incerteza sobre a qualidade das sequências encontradas, provando matematicamente o ótimo global ($\text{Gap} = 0,00\%$) para todos os cinco cenários.
2. **Recomendação para Operação Diária (Chão de Fábrica):** Recomenda-se a adoção do **GRASP com $\alpha = 0,3$ e VND (`Inserção + Swap + Bloco`)** como motor principal de programação da produção. Ele reproduziu $100\%$ dos ótimos globais comprovados pelo método exato em um tempo médio de apenas **$15,17\text{ s}$ por cenário** ($28,3\times$ mais rápido que o solver exato), oferecendo escalabilidade imediata para reprogramações dinâmicas em caso de quebra de máquina ou entrada de pedidos urgentes.
3. **Recomendação para Auditoria e Benchmarking:** O **Branch-and-Bound Combinatório** deve ser mantido como ferramenta de referência para validação de novos cenários ou auditoria periódica de planos mestres, dado que sua formulação livre de *Big-M* permite certificar otimalidade global em instâncias de até $25$ ordens de produção em poucos minutos.