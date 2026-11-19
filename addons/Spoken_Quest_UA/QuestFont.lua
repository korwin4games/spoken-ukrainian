local SU = assert(SpokenUkrainian)
local path = "Interface\\AddOns\\Spoken_Quest_UA\\NotoSans-Regular.ttf"

function SU:CaptureQuestFont(widget)
    if type(widget.GetFont) ~= "function" or type(widget.SetFont) ~= "function" then return end
    local native, size, flags = widget:GetFont()
    if type(native) == "string" and type(size) == "number" then
        return {native, size, flags}
    end
end

function SU:UseQuestFont(widget, original, ukrainian)
    if not original then return true end
    local selected = ukrainian and path or original[1]
    if widget:GetFont() == selected then return true end
    local ok, applied = pcall(widget.SetFont, widget, selected, original[2], original[3])
    return ok and applied ~= false
end
