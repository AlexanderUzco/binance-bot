const startStopLossCooldown = () => {
  const stopLossCooldown = new Date();
  stopLossCooldown.setMinutes(stopLossCooldown.getMinutes() + 10);
  return stopLossCooldown.getTime();
};

export { startStopLossCooldown };
