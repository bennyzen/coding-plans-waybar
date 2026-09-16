--!nonstrict
-- Bar capsule over `coding-plans-bar --provider <id>`.
--
-- The upstream Waybar entry point already returns everything needed as one JSON
-- line, so this file does no usage maths of its own:
--   text       -- the label, already "5h%·weekly%"
--   class      -- fresh | stale | critical | exhausted | empty
--   tooltip    -- a Pango block (stripped below; Noctalia does not render Pango)
--   percentage -- worst window, unused here because `text` carries both
--
-- Settings are per-instance, so a second capsule follows a second provider.

local provider = noctalia.string.trim(tostring(noctalia.getConfig("provider") or "claude"))
local glyphName = noctalia.string.trim(tostring(noctalia.getConfig("glyph") or "brain"))
local iconPath = noctalia.string.trim(tostring(noctalia.getConfig("icon_path") or ""))
local showGlyph = noctalia.getConfig("show_glyph") ~= false
local showName = noctalia.getConfig("show_name") == true

-- Brand SVGs ship with coding-plans-waybar. Prefer the colour variant, fall back
-- to the mono one, and only then to the icon font -- an installed tree can be
-- older than the checkout and lack a given `-color.svg`.
local ICON_DIRS = {
    "~/.local/share/coding-plans-waybar/icons",
    "~/.local/share/coding-plans-waybar/lib/coding_plans/providers/icons",
    "~/repos/coding-plans-waybar/lib/coding_plans/providers/icons",
}

local function resolveIcon()
    if iconPath ~= "" then
        local explicit = noctalia.expandPath(iconPath)
        if noctalia.fileExists(explicit) then return explicit end
        return nil
    end
    for _, dir in ipairs(ICON_DIRS) do
        for _, suffix in ipairs({ "-color.svg", ".svg" }) do
            local candidate = noctalia.expandPath(dir .. "/" .. provider .. suffix)
            if noctalia.fileExists(candidate) then return candidate end
        end
    end
    return nil
end

-- Resolved once: the file set does not change while the bar is up, and probing
-- it every render would stat four paths per capsule per tick.
local resolvedIcon = resolveIcon()

-- Severity comes from the CLI, not from re-reading the percentages: the upstream
-- thresholds are the ones the popup and the Waybar CSS already agree on.
local CLASS_COLOR = {
    fresh = "on_surface",
    stale = "on_surface_variant",
    critical = "secondary",
    exhausted = "error",
    empty = "on_surface_variant",
}

local latest = nil
local failed = false
local render

local function intervalMs()
    local minutes = tonumber(noctalia.getConfig("refresh_minutes")) or 5
    if minutes < 1 then minutes = 1 end
    return math.floor(minutes * 60 * 1000)
end

-- `%b<>` takes balanced angle brackets, which is every tag the upstream tooltip
-- emits. Entities are unescaped afterwards so `&amp;` does not reach the label.
local function stripPango(text)
    local out = tostring(text or ""):gsub("%b<>", "")
    out = out:gsub("&amp;", "&"):gsub("&lt;", "<"):gsub("&gt;", ">")
    out = out:gsub("&#39;", "'"):gsub("&quot;", '"')
    return out
end

-- Noctalia tooltips are key/value rows, the upstream one is a block of lines.
-- Each line becomes its own row. Lines with no word character are the drawn
-- rules ("────"), which carry nothing once the colour is gone.
local function tooltipRows()
    local raw = latest ~= nil and tostring(latest.tooltip or "") or ""
    local rows = {}
    for line in (stripPango(raw) .. "\n"):gmatch("(.-)\n") do
        local trimmed = noctalia.string.trim(line)
        if trimmed ~= "" and trimmed:match("%w") then
            rows[#rows + 1] = { key = "", value = trimmed }
        end
    end
    if failed then
        rows[#rows + 1] = { key = "coding-plans", value = "last read failed" }
    end
    if #rows == 0 then
        rows[1] = { key = "coding-plans", value = "no reading yet for '" .. provider .. "'" }
    end
    return rows
end

render = function()
    local class = latest ~= nil and tostring(latest.class or "fresh") or "empty"
    -- A failed read recolours the last good numbers rather than erasing them;
    -- blanking the capsule on a transient spawn failure just makes the bar jump.
    local color = failed and "error" or (CLASS_COLOR[class] or "on_surface")

    local children = {}
    if showGlyph then
        if resolvedIcon ~= nil then
            -- The brand mark says which provider, never how full it is, so it is
            -- not tinted by severity; the reading beside it carries that.
            children[#children + 1] = ui.image({ path = resolvedIcon, width = 14, height = 14, fit = "contain" })
        else
            children[#children + 1] = ui.glyph({ name = glyphName, size = 14, color = color })
        end
    end
    if showName then
        children[#children + 1] = ui.label({
            text = provider, fontSize = 11, color = "on_surface_variant", maxLines = 1,
        })
    end
    children[#children + 1] = ui.label({
        text = latest ~= nil and tostring(latest.text or "—") or "—",
        fontSize = 11,
        fontWeight = "semibold",
        color = color,
        maxLines = 1,
    })

    barWidget.render(ui.row({ gap = 5, align = "center" }, children))
    barWidget.setTooltip(tooltipRows())
end

local function poll()
    local started = noctalia.runAsync(
        "coding-plans-bar --provider " .. provider,
        function(result)
            local decoded = result ~= nil and not result.timedOut
                and noctalia.json.decode(result.stdout or "") or nil
            if type(decoded) == "table" and decoded.text ~= nil then
                latest = decoded
                failed = false
            else
                failed = true
            end
            render()
        end,
        30000
    )
    -- A refusal to spawn never calls back, so say so rather than showing a
    -- reading that nothing is refreshing.
    if not started then
        failed = true
        render()
    end
end

function onClick()
    -- The upstream popup is a full GTK window and owns its own layout; there is
    -- no Noctalia panel to duplicate it.
    --
    -- No callback: the callback form captures output and kills the child when
    -- its timeout expires, which closed the popup ~10 s after every click. The
    -- bare form starts a detached process and leaves it alone.
    noctalia.runAsync("coding-plans-popup")
end

render()
poll()
noctalia.setUpdateInterval(intervalMs())

function update()
    poll()
end
