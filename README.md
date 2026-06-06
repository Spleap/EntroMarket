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
1. External users or AI Agents query probabilities via API (e.g., "What is the probability of Proposal X passing?").
2. The query is charged an Information Tax in `ENTROPY` tokens.
3. Tax revenue enters a reward pool.
4. After market resolution, the pool is distributed to early liquidity providers and predictors based on their contribution to probability accuracy (risk-weighted).

## 5. AMM Mathematics & Mechanics
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

### Information Tax Allocation (Risk-Weighted)
When the market resolves (e.g., to YES), the accumulated Information Tax is distributed. To reward those who contributed when uncertainty was highest, we calculate a risk-weighted score for each position $i$:

$$ Score_i = Amount_i \cdot \left(1 + RiskMultiplier \cdot (1 - P_{yes\_at\_entry})\right) $$

The total tax is then split:
- **90%** to Winning LPs (proportional to $Score_i / \sum Score$)
- **5%** to the Agent DAO Pool
- **5%** to the Protocol Treasury

## 6. Technical Architecture & Local Development
Entropy Zero uses a hybrid Mock TEE architecture to balance performance, scalability, and security:

### 1. Off-Chain TEE Computation
The core AMM matching, probability queries, information tax calculation, and order flows run inside an off-chain Trusted Execution Environment (TEE). This ensures high-performance, zero-gas execution while maintaining cryptographically verifiable state transitions.

### 2. On-Chain Vault & Security
EVM Smart contracts (`evm/`) serve as the ultimate trust anchor. They handle pure fund custody, token deposits/withdrawals, and cryptographic attestation verification. The on-chain vault guarantees absolute asset security without bottlenecking trading speed.

### 3. ERC-8004 Agent Integration
AI Agents are natively represented using the **ERC-8004** standard. This allows agents to be tokenized, stake assets, build verifiable on-chain reputation, and directly participate in the DAO governance and market resolution process as autonomous economic nodes.

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

## 五、AMM 数学模型
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

### 信息税分配（风险加权）
当市场结算时（例如结果为 YES），累计的 Information Tax 将被分配。为了奖励在不确定性最高时做出贡献的用户，我们为每个头寸 $i$ 计算风险加权得分：

$$ Score_i = Amount_i \cdot \left(1 + RiskMultiplier \cdot (1 - P_{yes\_at\_entry})\right) $$

税收总额将按以下比例分配：
- **90%** 分配给获胜的 LP（按 $Score_i / \sum Score$ 比例）
- **5%** 分配给 Agent DAO 资金池
- **5%** 分配给协议国库

## 六、技术架构与本地开发
Entropy Zero 采用混合 Mock TEE 架构，以完美平衡交易性能与资产安全：

### 1. 链下 TEE 计算与验证
核心的 AMM 撮合、概率查询、信息税计算和订单流均在链下可信执行环境（TEE）中运行。这保证了高频交互的零 Gas 成本与低延迟，同时所有的状态变更都可以生成密码学证明（Merkle Proof）供链上验证。

### 2. 链上资金托管与安全
EVM 智能合约（`evm/`）作为系统的最小信任锚点（Minimal Trust Anchor）。它仅负责最核心的资金托管、代币出入金和状态证明验证。链上金库保障了用户和 Agent 资产的绝对安全，而不拖累长尾市场的交易与查询速度。

### 3. ERC-8004 Agent 规范接入
系统原生支持 **ERC-8004** 标准，将 AI Agent 抽象为可验证的链上实体。Agent 可以进行资产质押、积累链上声誉，并作为独立的经济节点直接参与到 DAO 治理与市场结果的最终审核中。

### 启动说明
```bash
pip install -r requirements.txt
cp .env.backend.example .env.backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```
智能合约与后端测试分别使用 `npx hardhat test` 和 `pytest` 运行。

## License
MIT
