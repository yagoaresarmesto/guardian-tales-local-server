local controller = newclass("LocalRaidSandyCarryoverController")

function controller:init()
    self.handler = nil
end

function controller:use_late_update_frame()
    return true
end

function controller:late_update_frame_priority()
    return CS.Oak.UpdatePriorities.StageEvent
end

function controller:late_update_frame()
    local boss = stage:GetCharacter("raid_boss")
    if boss == nil then
        return
    end
    local damaged = boss.DamagedBehaviour
    if damaged == nil or damaged == self.handler then
        return
    end
    self.handler = damaged
    if damaged:GetType().FullName ~= "Oak.MonsterDamagedBehaviour" then
        return
    end
    local stats = boss.CharacterStatsBehaviour
    if stats == nil or stats:GetType().FullName ~= "Oak.GuildRaid2BossStatsBehaviour" then
        return
    end
    -- Sandy's AI has entered and installed its legacy handler. Restore the
    -- handler the Raid character generator normally assigns to the main boss.
    local carryover = CS.Oak.PhoenixDamagedBehaviour()
    boss.DamagedBehaviour = carryover
    self.handler = carryover
    CS.UnityEngine.Debug.Log("Local Raid: restored Sandy damage carryover")
end

return {
    create = function()
        return controller()
    end
}
