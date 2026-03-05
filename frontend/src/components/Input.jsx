import { colors, radii, typography } from "../theme.js";

/** Shared input — consistent with theme */
export default function Input({ className = "", style = {}, ...props }) {
  return (
    <input
      className={className}
      style={{
        fontFamily: typography.fontMono,
        fontSize: typography.sizeLg,
        padding: "10px 12px",
        background: colors.inputBg,
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        border: `1px solid ${colors.inputBorder}`,
        borderRadius: radii.md,
        color: colors.text,
        outline: "none",
        width: "100%",
        boxSizing: "border-box",
        transition: "border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease",
        ...style,
      }}
      {...props}
    />
  );
}
