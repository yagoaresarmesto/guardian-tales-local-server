-- SPDX-License-Identifier: Apache-2.0
require('base/class')
local util = require('xlua/util')

local Controller = newclass('LocalClassicCoop')
local Oak = CS.Oak
local Unity = CS.UnityEngine
local stage_id = 303050001
local card_text = 'Classic Co-op\nFire Defense (Easy)\nSolo practice'

local function bind_result_exit(game)
    local result = Oak.UI.CoopResult.Instance
    if not result or not result.gameObject.activeInHierarchy then
        return false
    end
    local button = result.transform:Find('Content/Result/Exit Button')
    if not button then
        return false
    end
    local exiting = false
    CS.EventDelegate.Set(button:GetComponent(typeof(CS.UIButton)).onClick, function()
        if not exiting then
            exiting = true
            Unity.Debug.Log('[LocalClassicCoop] Returning from Defense results')
            game:StageToLobby(false, nil, false, nil)
        end
    end)
    Unity.Debug.Log('[LocalClassicCoop] Defense results exit ready')
    return true
end

local function launch(user)
    local party = user.Party
    local leader = assert(party and party.Count > 0 and party[0], 'Select a normal party leader')
    local hero_id = leader.Id
    assert(hero_id > 0, 'The normal party leader has no owned hero ID')
    local arena = assert(Oak.UserArena.Me, 'No local Arena profile is loaded')

    local entry = Oak.CoopEntry()
    entry.User = user
    entry.UserArena = arena
    entry.IsReady = true

    local slots = CS.System.Array.CreateInstance(typeof(Oak.CoopEntry), 1)
    slots[0] = entry
    local coop = Oak.Coop()
    coop.Slots = slots
    coop.Observers = CS.System.Array.CreateInstance(typeof(Oak.User), 0)
    coop.CoopId = stage_id
    coop.StageId = stage_id
    coop.HostUserId = user.Id:GetDecrypted()
    coop.Mode = Oak.CoopMode.Defense

    local spec = assert(coop.StageSpec, 'Fire Defense stage is missing')
    local previous_hero = arena.EscapeParty
    local previous_matching = spec.UnifiedMatching
    assert(type(previous_matching) == 'boolean', 'Fire Defense matching settings are missing')
    local restored = false
    local function restore_trial()
        if restored then
            return
        end
        restored = true
        if arena.EscapeParty == hero_id then
            arena.EscapeParty = previous_hero
        end
        spec.UnifiedMatching = previous_matching
    end
    local game = Oak.Game.Instance
    local ok, reason = pcall(function()
        -- Shared tier balancing needs an active online season. Solo practice
        -- uses the stage's own Easy settings for the duration of the run.
        spec.UnifiedMatching = false
        arena.EscapeParty = hero_id
        Oak.CoopClient.Instance:SetCoop(coop)
        local stage = assert(Oak.CoopStage.Create(stage_id), 'Fire Defense stage is missing')
        CS.Foundations.CoroutineManager.Instance:StartCoroutine(game, util.cs_generator(function()
            local deadline = Unity.Time.realtimeSinceStartup + 90
            while not stage.StageLoaded and Unity.Time.realtimeSinceStartup < deadline do
                coroutine.yield(nil)
            end
            local exit_bound = false
            while stage.StageLoaded and Oak.Stage.Instance == stage do
                if not exit_bound then
                    exit_bound = bind_result_exit(game)
                end
                coroutine.yield(nil)
            end
            restore_trial()
        end))
        Unity.Debug.Log('[LocalClassicCoop] Launching Fire Defense')
        game:LobbyToStage(stage, restore_trial, nil)
    end)
    if not ok then
        restore_trial()
        error(reason)
    end
end

function Controller:initialize(item)
    local card = item.gameObject
    local labels = card.transform:Find('EmptyDeco')
    self.label = labels:GetComponent(typeof(CS.UILabel))
    self.label.text = card_text
    CS.NGUITools.AddWidgetCollider(card)
    self.button = card:AddComponent(typeof(CS.UIButton))
    CS.EventDelegate.Set(self.button.onClick, function()
        if self.loading then
            return
        end
        self.loading = true
        self.label.text = 'Opening Fire Defense...'
        local function failure(reason)
            self.loading = false
            if self.button then
                self.label.text = card_text .. '\nTap to retry'
            end
            Unity.Debug.LogError('[LocalClassicCoop] ' .. tostring(reason))
        end
        local sent, err = pcall(function()
            local user = assert(Oak.User.Me, 'No local player is signed in')
            Oak.NetworkManager.ApiConnection:SendEscapeRequestCreate(stage_id, true)
                :Then(function()
                    if self.button then
                        local ok, reason = pcall(launch, user)
                        if not ok then
                            failure(reason)
                        end
                    end
                end)
                :Catch(failure)
        end)
        if not sent then
            failure(err)
        end
    end)
    Unity.Debug.Log('[LocalClassicCoop] Challenge card ready')
end

function Controller:dispose()
    if self.button then
        self.button.onClick:Clear()
        self.button = nil
    end
end

return {create = function() return Controller() end}
