using UnityEngine;


public class GenricEventUtilityClasses { } 

public class UpdateBalanceUI : GameEvent
{
    public string amount;
    public UpdateBalanceUI(string amount)
    {
        this.amount = amount;
    }
}

public class UpdateTimerUI : GameEvent
{
    public int time;
    public UpdateTimerUI(int time)
    {
        this.time = time;
    }
}

public class SetBetUI : GameEvent
{
    public bool canBet;
    public SetBetUI(bool canBet)
    {
        this.canBet = canBet;
    }
}

public class ShowDice : GameEvent
{
    public int[] values;
    public ShowDice(int[] values)
    {
        this.values = values;
    }
}

public class ShowPayoutMessage : GameEvent
{
    public string message;
    public ShowPayoutMessage(string message)
    {
        this.message = message;
    }
}

public class RoundStatusChangedUI : GameEvent
{
    public RoundStatus status;
    public RoundStatusChangedUI(RoundStatus status)
    {
        this.status = status;
    }
}

public class DiceRollWarning : GameEvent
{
    public int diceRollTime;
    public DiceRollWarning(int diceRollTime)
    {
        this.diceRollTime = diceRollTime;
    }
}
