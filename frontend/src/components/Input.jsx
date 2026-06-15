import { colors, radii, typography, liquidGlass } from "../theme.js";

export default function Input({ className = "", style = {}, ...props }) {
  return (
    <input
      className={className}
      style={{
        fontFamily: typography.fontMono,
        fontSize: typography.sizeLg,
        padding: "10px 12px",
        color: colors.text,
        outline: "none",
        width: "100%",
        boxSizing: "border-box",
        ...liquidGlass.input,
        ...style,
      }}
      {...props}
    />
  );
}
