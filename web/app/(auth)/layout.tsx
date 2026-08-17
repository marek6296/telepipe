// Auth stránky zdieľajú monochrómnu sadu tried s landingom.
// Zámerne NIE v globals.css — ten vlastní appka (`.app-*`).
import "../landing.css";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  // `contents` = wrapper nevytvára box, flex layout <body> ostáva nedotknutý;
  // slúži len na scope `.lp-*` tried a CSS premenných.
  return <div className="lp-scope contents">{children}</div>;
}
