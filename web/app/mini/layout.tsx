import type { Metadata, Viewport } from "next";
import "./mini.css";
export const metadata:Metadata = {title:"Social sites",robots:{index:false,follow:false}};
export const viewport:Viewport = {width:"device-width",initialScale:1,viewportFit:"cover",interactiveWidget:"resizes-content"};
export default function MiniLayout({children}:{children:React.ReactNode}) { return children; }
