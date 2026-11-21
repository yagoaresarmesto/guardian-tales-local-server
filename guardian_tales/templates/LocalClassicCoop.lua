-- SPDX-License-Identifier: Apache-2.0
require('base/class')

local Controller = newclass('LocalClassicCoop')
local Oak = CS.Oak
local Unity = CS.UnityEngine
local stage_id = 303050001
local card_text = 'Classic Co-op\nFire Defense (Easy)\nSolo practice'

local function launch(user)
    local entry = Oak.CoopEntry()
    entry.User = user
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
    Oak.CoopClient.Instance:SetCoop(coop)

    local stage = assert(Oak.CoopStage.Create(stage_id), 'Fire Defense stage is missing')
    Unity.Debug.Log('[LocalClassicCoop] Launching Fire Defense')
    Oak.Game.Instance:LobbyToStage(stage, nil, nil)
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
