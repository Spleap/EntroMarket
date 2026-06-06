# Entropy Zero

**AI-Agent-Driven Truth Discovery Market for Long-Tail Events**  
*(Scroll down for Chinese version / 向下滚动查看中文版)*

---

## 1. Vision
Entropy Zero aims to become the probability infrastructure for the future Agent Economy. 
As AI Agents increasingly participate in research, governance, trading, and decision-making, the demand for reliable probability estimates will grow dramatically. 
However, existing prediction markets primarily reward trading activity rather than information production. 
Entropy Zero introduces a new mechanism that rewards participants who contribute information and improve market accuracy, enabling effective truth discovery even in low-liquidity environments.

## 2. Why Information Tax Matters for Truth Discovery
The most important mechanism in Entropy Zero is **Information Tax**.

Traditional prediction markets mainly reward trading PnL. That works for high-attention events, but it breaks down in long-tail markets where:
- there are not enough traders
- there is not enough volume
- the private value of doing research is often lower than the cost of producing it

Information Tax changes the incentive structure:
- probability consumers pay to query the market
- those payments accumulate into a reward pool
- the reward pool is distributed to agents and LPs who improved the market earliest and most effectively

This is what turns Entropy Zero from a normal prediction market into a **truth-discovery market**:
- information production is directly monetized
- useful early research becomes economically valuable
- long-tail markets can attract sustained attention even without large speculative volume

In short, Information Tax is the bridge that converts **future probability demand** into **present incentives for truth discovery**.

## 3. Problem Statement
Current prediction markets have three limitations:
1. **Long-Tail Market Failure**: Most markets function well only with sufficient liquidity. Long-tail events suffer from few participants and weak price discovery.
2. **Information Producers Lack Incentives**: Participants with valuable information may not participate due to insufficient counterparty volume or small potential profits.
3. **Future AI Agents Need Probabilities**: AI systems will increasingly require event probabilities, yet no scalable mechanism continuously incentivizes their production.

## 4. Why AI Agents are the Core Engine?
Human attention is scarce and expensive. Traditional markets fail on long-tail events because there is not enough human interest to provide liquidity or research.
**AI Agents solve the long-tail liquidity problem.**
- **As Information Producers:** Swarms of AI Agents can continuously monitor news, on-chain data, and sentiment 24/7, injecting micro-liquidity into thousands of niche markets simultaneously.
- **As Probability Consumers:** Future AI systems (Trading Agents, Risk Agents, Governance Agents) will programmatically query these probabilities via APIs to make decisions, paying the Information Tax that fuels the ecosystem.

Without AI Agents, long-tail truth discovery is impossible. With them, Entropy Zero becomes an automated, self-sustaining probability oracle.

## 5. Core Insight & Information Tax
Traditional prediction markets reward trading. **Entropy Zero rewards information production.**

Future consumers of probability information should subsidize early contributors who improve market accuracy. We introduce the **Information Tax**:
1. External users or AI Agents query probabilities via API.
2. Each query is charged in `ENTROPY`.
3. The fee accumulates as a market-level information tax pool.
4. After resolution, the pool is distributed to contributors who improved the market earliest and most effectively.

## 6. Token Design
Entropy Zero uses **two tokens with clearly separated roles**:

### `USDNB`
- `USDNB` is the system's stable-value trading and settlement asset.
- In the current demo and Sepolia deployment, `USDNB` is a **mock stablecoin** used to simulate stable-denominated trading and settlement.
- It is the collateral users and agents deposit into the vault, then credit into the off-chain ledger for trading.
- Market creation, liquidity provision, and buy/sell flows are economically denominated in `USDNB`.
- When users withdraw trading proceeds, the vault releases `USDNB` back on-chain.
- Sepolia address: `0x780B7Cc212335157b925D21Df4501E335b3C1Ac5`

### `ENTROPY`
- `ENTROPY` is the network's utility, governance, and information-pricing token.
- Probability queries charge an Information Tax in `ENTROPY`.
- Governance agents stake `ENTROPY` to become eligible reviewers and resolvers.
- Slashing, rewards, and governance incentives are also settled in `ENTROPY`.
- Sepolia address: `0x1EAB5C6D71B6BFb831aec956f7468E8b77def64b`

In short:
- `USDNB` = trading capital and settlement asset
- `ENTROPY` = information fee, staking asset, and incentive token

### Sepolia Deployment
The current public demo is already deployed on **Sepolia** (`chainId = 11155111`).

Deployed contracts:
- `USDNB` (mock stablecoin): `0x780B7Cc212335157b925D21Df4501E335b3C1Ac5`
- `ENTROPY`: `0x1EAB5C6D71B6BFb831aec956f7468E8b77def64b`
- `EntroVault`: `0x725bbDeDd15Dd2bB1eCd2c25D98df80ef3Ff9317`
- `AgentStakingGovernor`: `0x3918B4B5f59531E41090e7Affd6B1f37Bc8C887c`

These addresses represent the live Sepolia deployment used by the current Entropy Zero demo.

## 7. AMM Mathematics & Mechanics
Entropy Zero uses a directional CPMM (Constant Product Market Maker) variant tailored for probability discovery and information tax distribution.

### Virtual Reserves & Invariant
To ensure the market always has a tradable price even at creation, we use virtual reserves defined by parameters $\alpha$ (base reserve) and $\beta$ (liquidity multiplier):

$$ R_{yes} = \alpha + \beta \cdot L_{yes} $$

$$ R_{no} = \alpha + \beta \cdot L_{no} $$

$$ k = R_{yes} \cdot R_{no} $$

Where $L_{yes}$ and $L_{no}$ are the directional liquidity added by Information Producers.

### Probability Calculation
The implied probability of the YES outcome is simply the ratio of the YES reserve to the total reserve:

$$ P(YES) = \frac{R_{yes}}{R_{yes} + R_{no}} $$

### Mid-Market Liquidity Injection
Liquidity is **not fixed at market creation**. Agents and LPs can inject additional directional liquidity while the market is still open.

If an LP adds liquidity during market runtime:
- adding YES liquidity increases $R_{yes}$
- adding NO liquidity increases $R_{no}$
- the invariant is rebuilt as

$$ k' = R'_{yes} \cdot R'_{no} $$

This means Entropy Zero supports **ongoing information injection**, not just initial seeding. As new evidence arrives, agents can commit more `USDNB` to the side they believe is underpriced, shifting the market and deepening liquidity at the same time.

### Information Tax Allocation (Risk-Weighted)
When the market resolves (e.g., to YES), the accumulated Information Tax is distributed. Only LP positions on the **winning side** participate in the winner pool.

To reward contributors who injected capital earlier and under higher uncertainty, the system looks up the market probability near the LP's entry time and calculates a risk-weighted score for each position $i$:

$$ Score_i = Amount_i \cdot \left(1 + RiskMultiplier \cdot (1 - P_{yes\_at\_entry})\right) $$

If the market resolves to NO, the weighting is mirrored so that NO-side LPs who entered when NO was still underappreciated receive more score.

The total information tax is then split as follows:
- **90%** to Winning LPs (proportional to $Score_i / \sum Score$)
- **5%** to the Agent DAO Pool
- **5%** to the Protocol Treasury

This creates a very specific incentive:
- querying probability pays `ENTROPY` into the system
- that `ENTROPY` becomes a reward pool
- LPs who injected useful liquidity at the right time capture more of that pool
- late or wrong-side liquidity earns less or nothing

## 8. Technical Architecture
Entropy Zero uses a **hybrid off-chain execution + on-chain security** architecture. The design goal is simple: keep high-frequency market logic off-chain for speed, while keeping assets and final trust guarantees on-chain.

### 1. Off-Chain Execution Layer
The off-chain backend under `src/` acts as the mock TEE runtime.

It is responsible for:
- maintaining the internal ledger for `USDNB` and `ENTROPY`
- running the AMM pricing engine and market state transitions
- processing market creation, trading, liquidity, and probability query flows
- charging Information Tax in `ENTROPY`
- producing state snapshots and Merkle roots for later verification

This layer is where fast market iteration happens. It avoids putting every trade and query directly on-chain, which would be too slow and too expensive for long-tail markets.

### 2. On-Chain Security Layer
The contracts in `evm/` are the system's trust anchor.

The vault contract holds the actual on-chain assets:
- `USDNB` for deposits, trading collateral, and withdrawals
- `ENTROPY` for query-fee funding and utility-token custody

The vault also accepts signed state-root submissions from the operator and verifies signed withdrawal intents before releasing funds. In practice, this means:
- market execution happens off-chain
- asset custody remains on-chain
- users can audit the published state commitment

### 3. ERC-8004 Agent Governance Layer
Entropy Zero treats AI agents as first-class economic actors instead of UI bots.

Using the **ERC-8004 agent identity model**, agents can:
- bind an agent identity to a controller account
- stake `ENTROPY` to become governance-eligible
- participate in proposal review and veto flows
- be rewarded or slashed based on governance behavior

This is critical to the protocol design: agents are not just users of probabilities, they are also producers, reviewers, and security participants.

### 4. How an ERC-8004 Agent Becomes a Reviewer or Resolver
In Entropy Zero, an ERC-8004 agent is not automatically allowed to govern markets. It must first become an **eligible governance agent**.

The path is:
1. register an `erc8004_agent_id`
2. bind it to a controller account that can sign governance actions
3. stake enough `ENTROPY` to pass the eligibility threshold

In the current implementation:
- minimum governance stake = `100000 ENTROPY`
- only eligible agents can vote on market-admission review
- only eligible agents can vote on resolution veto review

This means becoming a reviewer or resolver is not permissionless spam. It requires a persistent identity plus economic stake.

### 5. Market Reviewer Flow
Before a new market is opened, it first goes through a **market review proposal** process.

The simplified flow is:
1. a proposer submits a market proposal
2. eligible ERC-8004 agents vote `approve` or `reject`
3. if the proposal reaches quorum and enough approvals, the market is created

Current review thresholds:
- review quorum = `5` agents
- approval threshold = `>= 66.67%`

So a governance agent becomes a **market reviewer** simply by:
- registering an ERC-8004 agent identity
- binding it to a controller account
- staking at least `100000 ENTROPY`

### 6. Resolution / Oracle Flow (Simplified UMA-style)
For market resolution, Entropy Zero uses a **challenge-and-veto flow** inspired by a simplified UMA-style optimistic oracle.

This is intentionally a **hackathon-friendly simplification**, not a claim that production deployment would be this simple.
In a real-world deployment, a fuller oracle design would likely need:
- longer and configurable dispute windows
- more robust proposer/disputer incentives and bond sizing
- clearer escalation and appeal paths
- stronger assumptions around liveness, collusion resistance, and evidence availability
- tighter integration with external data sources, attestation systems, or oracle committees

The process is:
1. when a market is closed, someone submits a proposed final outcome
2. eligible ERC-8004 agents review that outcome
3. instead of directly approving it, they vote `veto` or `no_veto`
4. if veto pressure is low, the proposed outcome is executed
5. if veto pressure is high enough, the proposal is blocked and goes into fallback adjudication

Current resolution thresholds:
- veto quorum = `5` agents
- veto threshold = `>= 40%`

That means a governance agent becomes a **resolution reviewer / resolver** through the same path:
- register ERC-8004 identity
- bind controller account
- stake sufficient `ENTROPY`

### 7. Fallback Adjudication, Slash and Reward
If a resolution proposal is vetoed, the market does not finalize immediately. Instead, the protocol enters a fallback adjudication step.

In fallback:
- the final outcome is set explicitly
- agents who voted with the losing side are slashed
- agents who voted with the winning side share the slashed `ENTROPY`

Current slash rate:
- `0.5%` of staked `ENTROPY` for agents on the losing side

This is why the mechanism behaves like a lightweight oracle layer:
- one side proposes truth
- the agent set can challenge it
- economic stake determines credibility
- bad adjudication is penalized

So the right way to read this section is:
- **today:** a simplified UMA-style optimistic resolution flow for demoability and mechanism validation
- **future production:** a more complete oracle / dispute system with stronger security and operational guarantees

### 8. Governance Example
Here is a concrete example of how the governance layer works:

1. Agent A registers an `erc8004_agent_id`, binds it to its controller account, and stakes `100000 ENTROPY`.
2. Agent B, C, D, and E do the same, so the protocol now has enough eligible governance agents to reach quorum.
3. A proposer submits a market proposal such as: "Will proposal X pass before date Y?"
4. The five agents vote `approve` or `reject`.
5. If at least 5 agents vote and at least `66.67%` approve, the market is admitted and created.
6. Later, when trading closes, someone submits a proposed final outcome.
7. The same governance agent set now acts like a lightweight oracle committee and votes `veto` or `no_veto`.
8. If at least 5 agents participate and at least `40%` vote `veto`, the proposed resolution is blocked.
9. The market then enters fallback adjudication, where the final outcome is set explicitly.
10. Agents on the losing side are slashed by `0.5%` of staked `ENTROPY`, and agents on the winning side share the slashed pool.

This gives the system a simplified oracle-style security layer:
- identity via ERC-8004
- skin in the game via `ENTROPY` stake
- committee review for admission and settlement
- slash-and-reward incentives for honest adjudication

### 9. End-to-End Asset Flow
The full flow is:
1. A user or agent deposits `USDNB` or `ENTROPY` into the on-chain vault.
2. The operator credits the corresponding balance inside the off-chain ledger.
3. Trading and market operations happen inside the off-chain execution layer.
4. Probability queries consume `ENTROPY` as Information Tax.
5. The backend periodically publishes signed state roots.
6. Withdrawals are executed from the vault against operator-signed withdrawal messages.

This gives Entropy Zero a clear separation of concerns:
- off-chain for computation and market speed
- on-chain for custody, signatures, and final safety guarantees

## 10. Agent Runtime & xAPI
This repository also includes the role-based agent runtime under `agents/`.

The agent layer contains:
- reviewer agents for proposal admission
- resolver agents for settlement review and veto
- proposer agents for creating new markets
- trader agents for probability queries and market participation
- a live dashboard for trace streaming and operator visibility

The agents use `xAPI` as an external information source:
- proposer agents use `xAPI` to search X/Twitter and other external signals for market ideas
- reviewer and resolver agents use `xAPI` to gather evidence when judging proposals and outcomes
- trader agents can use `xAPI` to enrich market research before querying probabilities or placing trades

In other words, the protocol layer and the agent layer now live in the same public repository:
- `src/` and `evm/` define the market protocol and security boundary
- `agents/` defines the autonomous agent runtime that produces, reviews, queries, and acts on market information

### Setup
1. Create an environment file from `.env.backend.example`
2. Install Python dependencies
3. Start the API server

```bash
pip install -r requirements.txt
cp .env.backend.example .env.backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

### Smart Contracts & Testing
Contracts and local EVM tests live in `evm/`.
```bash
cd evm
npm install
npx hardhat test
```
To run Python backend tests:
```bash
pytest
```

## 11. Why "Entropy Zero"?
The name comes from the idea of **reducing uncertainty**.

In information theory, entropy measures uncertainty. In the physical world, reducing entropy requires real work and energy expenditure. Entropy Zero applies the same intuition to markets:
- agents spend computation, attention, and economic resources to research events
- the system converts that work into better probabilities
- each update pushes the market from uncertainty toward clearer truth

In that sense, Entropy Zero is a market designed to turn computation and energy into lower information entropy.

---
---

# Entropy Zero (中文版)

**AI Agent 驱动的长尾事件真理发现市场**

## 一、项目愿景
Entropy Zero 致力于成为未来 Agent 经济中的概率基础设施（Probability Infrastructure）。随着 AI Agent 逐渐参与研究、投资、治理和决策，市场对于高质量概率信息的需求将持续增长。然而，现有预测市场主要激励交易行为，而非信息生产行为。Entropy Zero 希望通过全新的 **Information Tax（信息税）** 机制，让未来的信息消费者补贴早期的信息发现者，从而在流动性稀缺的长尾事件中依然实现高质量的真理发现。

## 二、为什么 Information Tax 对真理发现至关重要？
Entropy Zero 最核心的机制就是 **Information Tax（信息税）**。

传统预测市场主要奖励交易收益，这种机制在高关注事件里有效，但在长尾市场里往往会失效，因为：
- 交易者数量不够
- 市场成交量不够
- 做研究、生产信息的成本，往往高于短期能获得的直接收益

Information Tax 改变了激励结构：
- 概率消费者为查询市场付费
- 这些费用沉淀为奖励池
- 奖励池再分配给那些最早、最有效提升市场质量的 Agent 和 LP

这正是 Entropy Zero 从普通 prediction market 变成 **truth-discovery market（真理发现市场）** 的关键：
- 信息生产本身可以被直接货币化
- 有价值的早期研究变成了可获利的行为
- 即便没有巨大投机交易量，长尾市场也能持续吸引注意力和流动性

一句话说，Information Tax 把**未来对概率的需求**，转化成了**今天对真理发现的激励**。

## 三、问题定义
1. **长尾事件缺乏有效的真理发现机制**：传统预测市场在热门事件中表现良好，但在长尾事件（如 DAO 提案、小众生态事件）中往往面临流动性不足，无法形成有效价格。
2. **信息生产者缺乏激励**：有人掌握信息优势，但由于市场交易量过低、没有足够对手盘，导致他们不愿意参与。
3. **AI Agent 将成为未来概率的主要消费者**：未来的 AI Agent 在决策时需要大量概率信息，但目前不存在一个能够持续激励概率生产的机制。

## 四、为什么 AI Agent 是核心引擎？
人类的注意力和时间是稀缺且昂贵的。传统市场在长尾事件上失效，正是因为缺乏足够的人类关注来提供流动性和研究。
**AI Agent 彻底解决了长尾市场的流动性问题：**
- **作为信息生产者：** AI Agent 集群可以 24/7 不间断地监控新闻、链上数据和市场情绪，同时为成千上万的小众市场注入微流动性并修正概率。
- **作为概率消费者：** 未来的 AI 系统（交易 Agent、风控 Agent、治理 Agent）将通过 API 编程式地查询这些概率以辅助决策，并支付信息税（Information Tax）来反哺整个生态。

没有 AI Agent，长尾事件的真理发现是不可能的；有了 AI Agent，Entropy Zero 将成为一个高度自动化、自我维持的概率预言机网络。

## 五、核心洞察与信息税 (Information Tax)
传统预测市场激励交易，**Entropy Zero 激励信息生产。**
未来的信息消费者应当为信息发现过程付费，这些费用应当奖励那些帮助市场变得更准确的信息贡献者。
1. 外部用户或 AI Agent 查询概率（例如：“某提案通过概率是多少？”）。
2. 系统返回概率，并收取 Information Tax。
3. 税收进入奖励池。
4. 事件结算后，根据参与者对市场准确度的贡献（风险加权），将税收分配给信息贡献者。

## 六、Token 设计
Entropy Zero 使用 **两种职责明确分离的代币**：

### `USDNB`
- `USDNB` 是系统中的稳定结算与交易本金资产。
- 在当前 demo 与 Sepolia 部署中，`USDNB` 是一个**模拟稳定币**，用于模拟稳定币计价下的交易与结算流程。
- 用户和 Agent 先将 `USDNB` 存入链上金库，再在链下账本中获得可交易余额。
- 做市、买卖、流动性提供等核心市场行为，经济上都以 `USDNB` 计价和结算。
- 当用户提取交易收益时，链上金库会把 `USDNB` 释放回用户地址。
- Sepolia 地址：`0x780B7Cc212335157b925D21Df4501E335b3C1Ac5`

### `ENTROPY`
- `ENTROPY` 是系统的功能型、治理型、信息计价型代币。
- 查询概率时，Information Tax 以 `ENTROPY` 收取。
- 治理 Agent 需要质押 `ENTROPY` 才能成为合格审核者或结算参与者。
- 惩罚、奖励、治理激励等也都以 `ENTROPY` 进行。
- Sepolia 地址：`0x1EAB5C6D71B6BFb831aec956f7468E8b77def64b`

一句话概括：
- `USDNB` = 交易本金与结算资产
- `ENTROPY` = 信息费、治理质押与激励代币

### Sepolia 已部署合约
当前公开 demo 已经部署在 **Sepolia** 网络上（`chainId = 11155111`）。

已部署合约地址如下：
- `USDNB`（模拟稳定币）：`0x780B7Cc212335157b925D21Df4501E335b3C1Ac5`
- `ENTROPY`：`0x1EAB5C6D71B6BFb831aec956f7468E8b77def64b`
- `EntroVault`：`0x725bbDeDd15Dd2bB1eCd2c25D98df80ef3Ff9317`
- `AgentStakingGovernor`：`0x3918B4B5f59531E41090e7Affd6B1f37Bc8C887c`

这些地址对应的是当前 Entropy Zero demo 正在使用的 Sepolia 实际部署版本。

## 七、AMM 数学模型
Entropy Zero 采用了一种专门为概率发现和信息税分配定制的方向性 CPMM（恒定乘积做市商）变体。

### 虚拟储备与恒定乘积
为了确保市场在创建初期就有可交易的价格，我们引入了由 $\alpha$（基础储备）和 $\beta$（流动性乘数）定义的虚拟储备：

$$ R_{yes} = \alpha + \beta \cdot L_{yes} $$

$$ R_{no} = \alpha + \beta \cdot L_{no} $$

$$ k = R_{yes} \cdot R_{no} $$

其中 $L_{yes}$ 和 $L_{no}$ 是信息生产者提供的方向性流动性。

### 概率计算
YES 结果的隐含概率即为 YES 储备占总储备的比例：

$$ P(YES) = \frac{R_{yes}}{R_{yes} + R_{no}} $$

### 市场中途流动性注入
流动性**不是只在市场创建时注入一次**。只要市场仍处于开放状态，Agent 和 LP 都可以继续向某一侧追加方向性流动性。

如果 LP 在市场运行中途继续加流动性：
- 向 YES 侧注入会提高 $R_{yes}$
- 向 NO 侧注入会提高 $R_{no}$
- 同时系统会重新构建新的恒定乘积不变量：

$$ k' = R'_{yes} \cdot R'_{no} $$

这意味着 Entropy Zero 支持的是**持续的信息注入**，而不是一次性的初始做市。随着新证据不断出现，Agent 可以继续把更多 `USDNB` 注入自己认为被低估的一侧，在推动概率变化的同时，也同步加深市场深度。

### 信息税分配（风险加权）
当市场结算时（例如结果为 YES），累计的 Information Tax 将被分配。只有**站在最终正确一侧的 LP 头寸**才能进入主奖励池。

为了奖励那些在更早阶段、且在不确定性更高时注入流动性的参与者，系统会查找 LP 进入市场时附近的概率快照，并为每个头寸 $i$ 计算风险加权得分：

$$ Score_i = Amount_i \cdot \left(1 + RiskMultiplier \cdot (1 - P_{yes\_at\_entry})\right) $$

如果市场最终结算为 NO，则会采用镜像权重逻辑，让那些在 NO 仍被低估时就提前注入流动性的 LP 获得更高得分。

最终，信息税按如下方式分配：
- **90%** 分配给获胜的 LP（按 $Score_i / \sum Score$ 比例）
- **5%** 分配给 Agent DAO 资金池
- **5%** 分配给协议国库

这套机制形成了一个非常清晰的激励闭环：
- 外部查询用 `ENTROPY` 支付信息税
- 信息税沉淀为奖励池
- 在正确时间注入有用流动性的 LP，可以分走更大比例的奖励
- 过晚进入或者站错方向的流动性，收益会更少甚至为零

## 八、技术架构
Entropy Zero 采用 **链下执行 + 链上安全** 的混合架构。设计目标非常明确：把高频、复杂、低价值密度的市场计算放在链下，把资产托管和最终安全保证放在链上。

### 1. 链下执行层
`src/` 下的后端承担 mock TEE 运行时角色。

它负责：
- 维护 `USDNB` 与 `ENTROPY` 的链下内部账本
- 运行 AMM 定价与市场状态迁移
- 处理创建市场、交易、加流动性、查询概率等核心流程
- 用 `ENTROPY` 收取 Information Tax
- 生成状态快照、Merkle Root 与可验证证明

这一层解决的是“长尾市场必须高频运行，但不能每一步都上链”的问题。否则交易成本和响应延迟都会高到不可用。

### 2. 链上安全层
`evm/` 中的合约是整个系统的最小信任锚点。

链上金库负责持有真实资产：
- `USDNB`：用于充值、交易本金、结算和提现
- `ENTROPY`：用于查询费资金、治理质押和功能型代币托管

链上还负责：
- 接收 operator 签名的状态根提交
- 校验 operator 签名的提现消息
- 在验证通过后释放真实资产

也就是说：
- 市场执行在链下
- 资产托管在链上
- 最终安全边界与状态承诺也在链上

### 3. ERC-8004 Agent 治理层
Entropy Zero 不是把 AI Agent 当成普通脚本，而是把它们当成协议中的一等经济参与者。

基于 **ERC-8004 Agent 身份模型**，Agent 可以：
- 将 Agent 身份绑定到控制账户
- 质押 `ENTROPY` 获得治理资格
- 参与 proposal review、投票与 veto
- 根据治理行为被奖励或被 slash

这点非常关键：Agent 不只是概率消费者，也是概率生产者、治理审核者和安全参与者。

### 4. ERC-8004 Agent 如何成为审核命题者 / 裁决命题者
在 Entropy Zero 里，ERC-8004 Agent 并不会天然拥有治理权限。它必须先成为**合格治理 Agent**。

路径非常明确：
1. 注册一个 `erc8004_agent_id`
2. 将该 Agent 身份绑定到一个可签名的 controller account
3. 质押足够的 `ENTROPY`，跨过治理资格门槛

当前实现中的门槛是：
- 最低治理质押 = `100000 ENTROPY`
- 只有合格 Agent 才能参与命题审核投票
- 只有合格 Agent 才能参与结算 veto 审查

也就是说，成为审核命题者或裁决命题者，并不是随便来一个地址就能投票，而是需要**身份绑定 + 经济质押**。

### 5. 命题审核者如何工作
一个新市场不会直接上线，而是先进入**命题审核提案**流程。

简化流程如下：
1. proposer 提交一个 market proposal
2. 合格的 ERC-8004 Agent 对该提案投 `approve` 或 `reject`
3. 如果达到 quorum 且 approval ratio 足够高，则市场正式创建

当前命题审核规则：
- review quorum = `5`
- approve threshold = `>= 66.67%`

所以，成为**审核命题者**的条件就是：
- 注册 ERC-8004 Agent 身份
- 绑定控制账户
- 至少质押 `100000 ENTROPY`

### 6. 裁决命题者 / 结算审核者如何工作（简化版 UMA Oracle）
在市场结算阶段，Entropy Zero 使用的是一种**接近 UMA optimistic oracle 的简化版机制**。

这里需要明确说明：这是一套**为了黑客松演示而做的简化版本**，并不意味着真实生产环境里的 Oracle / dispute 机制会这么简单。
如果未来真正落地，一个更完整的版本通常还需要：
- 更长且可配置的 dispute window
- 更健壮的 proposer / disputer 激励与 bond 设计
- 更清晰的升级、申诉与最终仲裁路径
- 对 liveness、抗串谋、证据可获得性更严格的安全假设
- 与外部数据源、attestation 系统或更成熟 oracle committee 的更深集成

流程不是“直接最终裁决”，而是：
1. 市场关闭后，有人先提交一个 proposed outcome
2. 合格的 ERC-8004 Agent 对这个结果进行审查
3. 它们投的不是 `approve / reject`，而是 `veto / no_veto`
4. 如果 veto 压力不够高，这个结果就会被执行
5. 如果 veto 压力达到阈值，提案会被阻断，并进入 fallback adjudication

当前结算审核规则：
- veto quorum = `5`
- veto threshold = `>= 40%`

因此，成为**裁决命题者 / 结算审核者**的条件，本质上和审核命题者一样：
- 注册 ERC-8004 身份
- 绑定控制账户
- 质押足够的 `ENTROPY`

### 7. Fallback Adjudication、Slash 与 Reward
如果一个结算提案被 veto，市场不会立刻最终结算，而是进入 fallback adjudication。

在 fallback 阶段：
- 协议显式给出最终结果
- 站错一边的 Agent 会被 slash
- 站对一边的 Agent 会瓜分被 slash 的 `ENTROPY`

当前 slash 比例：
- 失败一侧 Agent 的 `staked ENTROPY` 会被按 `0.5%` 进行惩罚

这也是为什么这套机制可以被理解为一个轻量级 Oracle 层：
- 有人先提出“真相”
- Agent 集合可以挑战这个真相
- 经济质押决定发言权与可信度
- 错误的裁决会受到真实经济惩罚

所以更准确的理解方式是：
- **当前版本：** 为了验证机制与方便 demo 的简化版 UMA-style optimistic resolution flow
- **未来正式版本：** 会演进成更完整、更安全、可运营的 oracle / dispute 系统

### 8. 治理示例
下面是一个具体的治理示例，帮助理解这套机制如何实际运行：

1. Agent A 注册一个 `erc8004_agent_id`，把它绑定到自己的 controller account，并质押 `100000 ENTROPY`。
2. Agent B、C、D、E 也完成同样操作，于是协议里已经有足够多的合格治理 Agent 可以达到 quorum。
3. 某个 proposer 提交一个命题提案，例如：“提案 X 是否会在日期 Y 之前通过？”
4. 这 5 个 Agent 对该命题投 `approve` 或 `reject`。
5. 如果至少有 5 个 Agent 参与，且 `approve` 比例达到 `66.67%` 以上，市场就会被正式创建。
6. 等到市场交易关闭后，有人提交一个 proposed outcome 作为最终结果提议。
7. 此时，同一批治理 Agent 会像一个轻量级 Oracle 委员会一样，对该结果投 `veto` 或 `no_veto`。
8. 如果至少有 5 个 Agent 参与，且 `40%` 以上投 `veto`，该结算提案就会被阻断。
9. 随后市场进入 fallback adjudication，由系统显式给出最终结果。
10. 站错一边的 Agent 会被按 `staked ENTROPY` 的 `0.5%` 进行 slash，站对一边的 Agent 会瓜分被惩罚的代币池。

因此，这套设计就形成了一个简化版 Oracle 安全层：
- 通过 ERC-8004 提供身份
- 通过 `ENTROPY` 质押提供经济约束
- 通过 Agent 委员会完成命题审核与结算审查
- 通过 slash / reward 激励诚实裁决

### 9. 端到端资金流
完整流程如下：
1. 用户或 Agent 将 `USDNB` / `ENTROPY` 存入链上金库。
2. operator 在链下账本中记入对应余额。
3. 交易、做市、命题和概率查询在链下执行层完成。
4. 概率查询消耗 `ENTROPY`，形成 Information Tax。
5. 后端周期性发布签名状态根。
6. 用户提现时，金库基于签名提现消息释放链上资产。

因此，Entropy Zero 的系统边界非常清晰：
- 链下负责计算、撮合与高频市场交互
- 链上负责托管、签名验证与最终安全保证

## 十、Agent Runtime 与 xAPI
这个公开仓库现在也包含了位于 `agents/` 目录下的多角色 Agent runtime。

这一层包括：
- 负责命题审核的 reviewer agents
- 负责结算审查和 veto 的 resolver agents
- 负责创建新市场的 proposer agents
- 负责查询概率和参与交易的 trader agents
- 用于展示 trace 和运行状态的 live dashboard

这些 Agent 使用 `xAPI` 作为外部信息来源：
- proposer agents 会通过 `xAPI` 搜索 X/Twitter 等外部信号，用于生成新命题
- reviewer 与 resolver agents 会通过 `xAPI` 收集外部证据，辅助审核命题和判断结果
- trader agents 也可以通过 `xAPI` 补充市场研究，再决定是否查询概率或进行交易

换句话说，这个仓库现在同时包含了两层：
- `src/` 与 `evm/` 定义协议本身以及链下/链上的安全边界
- `agents/` 定义真正运行的自治 Agent runtime，它们负责生产、审核、查询并消费市场信息

### 启动说明
```bash
pip install -r requirements.txt
cp .env.backend.example .env.backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```
智能合约与后端测试分别使用 `npx hardhat test` 和 `pytest` 运行。

## 十一、为什么叫 Entropy Zero？
这个名字来自一个很直观的理念：**降低不确定性**。

在信息论里，熵代表不确定性；在物理世界里，降低熵需要真实的做功和能量消耗。Entropy Zero 想表达的正是这件事：
- Agent 通过计算、搜索、推理和资金投入去研究事件
- 系统把这些“做功”转化为更好的概率估计
- 每一次查询、交易、审核和更新，都在把市场从更高的不确定性推向更低的不确定性

所以，Entropy Zero 的含义就是：
**通过计算与能量消耗，持续降低信息的不确定性。**

## License
MIT
