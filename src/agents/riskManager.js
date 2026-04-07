function calculatePositionSize({ accountBalance, riskPercent, entryPrice, stopPrice }) {
  if (!accountBalance || !riskPercent || !entryPrice || !stopPrice) {
    return { quantity: 0, riskAmount: 0, rewardRatio: 0 };
  }

  const riskAmount = accountBalance * (riskPercent / 100);
  const pipValue = 0.0001; // standard pip
  const stopPips = Math.abs(entryPrice - stopPrice) / pipValue;

  if (stopPips === 0) {
    return { quantity: 0, riskAmount: 0, rewardRatio: 0 };
  }

  const quantity = Math.max(0.01, Math.floor((riskAmount / (stopPips * pipValue * entryPrice)) * 100) / 100);
  
  return {
    quantity,
    riskAmount: riskAmount.toFixed(2),
    stopPips: stopPips.toFixed(2),
    exposure: (quantity * entryPrice).toFixed(2)
  };
}

function validateRisk({ quantity, entryPrice, accountBalance, maxLeverage = 20 }) {
  const exposure = quantity * entryPrice;
  const leverage = exposure / accountBalance;

  return {
    quantity,
    exposure: exposure.toFixed(2),
    leverage: leverage.toFixed(2),
    valid: leverage <= maxLeverage,
    warning: leverage > maxLeverage ? `Leverage ${leverage.toFixed(2)}x exceeds max ${maxLeverage}x` : null
  };
}

module.exports = { calculatePositionSize, validateRisk };
