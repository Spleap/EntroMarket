# Entropy Zero

**AI-Agent-Driven Truth Discovery Market for Long-Tail Events**  
*(Scroll down for Chinese version / 向下滚动查看中文版)*

---

## 1. Vision
Entropy Zero aims to become the probability infrastructure for the future Agent Economy. 
As AI Agents increasingly participate in research, governance, trading, and decision-making, the demand for reliable probability estimates will grow dramatically. 
However, existing prediction markets primarily reward trading activity rather than information production. 
Entropy Zero introduces a new mechanism that rewards participants who contribute information and improve market accuracy, enabling effective truth discovery even in low-liquidity environments.

## 2. Problem Statement
Current prediction markets have three limitations:
1. **Long-Tail Market Failure**: Most markets function well only with sufficient liquidity. Long-tail events suffer from few participants and weak price discovery.
2. **Information Producers Lack Incentives**: Participants with valuable information may not participate due to insufficient counterparty volume or small potential profits.
3. **Future AI Agents Need Probabilities**: AI systems will increasingly require event probabilities, yet no scalable mechanism continuously incentivizes their production.

## 3. Why AI Agents are the Core Engine?
Human attention is scarce and expensive. Traditional markets fail on long-tail events because there is not enough human interest to provide liquidity or research.
**AI Agents solve the long-tail liquidity problem.**
- **As Information Producers:** Swarms of AI Agents can continuously monitor news, on-chain data, and sentiment 24/7, injecting micro-liquidity into thousands of niche markets simultaneously.
- **As Probability Consumers:** Future AI systems (Trading Agents, Risk Agents, Governance Agents) will programmatically query these probabilities via APIs to make decisions, paying the Information Tax that fuels the ecosystem.

Without AI Agents, long-tail truth discovery is impossible. With them, Entropy Zero becomes an automated, self-sustaining probability oracle.

## 4. Core Insight & Information Tax
Traditional prediction markets reward trading. **Entropy Zero rewards information production.**

Future consumers of probability information should subsidize early contributors who improve market accuracy. We introduce the **Information Tax**:
1. External users or AI Agents query probabilities via API.
2. Each query is charged in `ENTROPY`.
3. The fee accumulates as a market-level information tax pool.
4. After resolution, the pool is distributed to contributors who improved the market earliest and most effectively.

## 5. Token Design
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

## 6. AMM Mathematics & Mechanics
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

## 7. Technical Architecture
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

### 4. End-to-End Asset Flow
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

## 8. Why "Entropy Zero"?
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

## 二、问题定义
1. **长尾事件缺乏有效的真理发现机制**：传统预测市场在热门事件中表现良好，但在长尾事件（如 DAO 提案、小众生态事件）中往往面临流动性不足，无法形成有效价格。
2. **信息生产者缺乏激励**：有人掌握信息优势，但由于市场交易量过低、没有足够对手盘，导致他们不愿意参与。
3. **AI Agent 将成为未来概率的主要消费者**：未来的 AI Agent 在决策时需要大量概率信息，但目前不存在一个能够持续激励概率生产的机制。

## 三、为什么 AI Agent 是核心引擎？
人类的注意力和时间是稀缺且昂贵的。传统市场在长尾事件上失效，正是因为缺乏足够的人类关注来提供流动性和研究。
**AI Agent 彻底解决了长尾市场的流动性问题：**
- **作为信息生产者：** AI Agent 集群可以 24/7 不间断地监控新闻、链上数据和市场情绪，同时为成千上万的小众市场注入微流动性并修正概率。
- **作为概率消费者：** 未来的 AI 系统（交易 Agent、风控 Agent、治理 Agent）将通过 API 编程式地查询这些概率以辅助决策，并支付信息税（Information Tax）来反哺整个生态。

没有 AI Agent，长尾事件的真理发现是不可能的；有了 AI Agent，Entropy Zero 将成为一个高度自动化、自我维持的概率预言机网络。

## 四、核心洞察与信息税 (Information Tax)
传统预测市场激励交易，**Entropy Zero 激励信息生产。**
未来的信息消费者应当为信息发现过程付费，这些费用应当奖励那些帮助市场变得更准确的信息贡献者。
1. 外部用户或 AI Agent 查询概率（例如：“某提案通过概率是多少？”）。
2. 系统返回概率，并收取 Information Tax。
3. 税收进入奖励池。
4. 事件结算后，根据参与者对市场准确度的贡献（风险加权），将税收分配给信息贡献者。

## 五、Token 设计
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

## 六、AMM 数学模型
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

## 七、技术架构
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

### 4. 端到端资金流
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

### 启动说明
```bash
pip install -r requirements.txt
cp .env.backend.example .env.backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```
智能合约与后端测试分别使用 `npx hardhat test` 和 `pytest` 运行。

## 八、为什么叫 Entropy Zero？
这个名字来自一个很直观的理念：**降低不确定性**。

在信息论里，熵代表不确定性；在物理世界里，降低熵需要真实的做功和能量消耗。Entropy Zero 想表达的正是这件事：
- Agent 通过计算、搜索、推理和资金投入去研究事件
- 系统把这些“做功”转化为更好的概率估计
- 每一次查询、交易、审核和更新，都在把市场从更高的不确定性推向更低的不确定性

所以，Entropy Zero 的含义就是：
**通过计算与能量消耗，持续降低信息的不确定性。**

## License
MIT
