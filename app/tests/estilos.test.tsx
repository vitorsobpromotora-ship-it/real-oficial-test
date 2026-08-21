/** Ponto 20 — seletor VISUAL de estilos: cards demonstrativos, agrupados por
 *  família, com o Palavra Pop Classic preservado. */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StylePicker from "../src/editor/StylePicker";
import type { CaptionPreset } from "../src/api/types";

const PRESETS: CaptionPreset[] = [
  { id: "bold_karaoke", label: "Karaokê Bold", family: "Clássicos", font_size: 74,
    font_family: "Montserrat", text_color: "#FFFFFF", highlight_color: "#FFD400",
    outline: 4, outline_color: "#000000", karaoke: true, word_mode: false },
  { id: "palavra_pop", label: "Palavra Pop Classic", family: "Palavra Pop",
    font_size: 96, font_family: "Montserrat", text_color: "#FFFFFF",
    highlight_color: "#FFFFFF", outline: 5, outline_color: "#000000", word_mode: true },
  { id: "pp_box", label: "Palavra Pop Box", family: "Palavra Pop", font_size: 84,
    font_family: "Montserrat", text_color: "#101010", back_color: "#FFFFFF",
    border_style: 3, outline: 6, word_mode: true },
];

describe("StylePicker", () => {
  it("agrupa por família, demonstra a amostra e marca o selecionado", () => {
    render(<StylePicker presets={PRESETS} valor="palavra_pop" onChange={vi.fn()} />);
    expect(screen.getByText("Clássicos")).toBeInTheDocument();
    expect(screen.getByText("Palavra Pop")).toBeInTheDocument();
    expect(screen.getByText("Palavra Pop Classic")).toBeInTheDocument();
    // amostra visível em cada card (frase completa ou palavra ativa)
    expect(screen.getAllByText(/LEGENDA/).length).toBeGreaterThanOrEqual(3);
    expect(screen.getByTestId("preset-palavra_pop").className).toContain("on");
    expect(screen.getByTestId("preset-pp_box").className).not.toContain("on");
  });

  it("clicar num card troca o preset e o botão de padrão limpa a escolha", () => {
    const onChange = vi.fn();
    render(<StylePicker presets={PRESETS} valor="palavra_pop" onChange={onChange} />);
    fireEvent.click(screen.getByTestId("preset-pp_box"));
    expect(onChange).toHaveBeenCalledWith("pp_box");
    fireEvent.click(screen.getByText("Usar o padrão do Kit de Marca"));
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("preset com caixa mostra fundo sólido; preset com contorno mostra outline", () => {
    render(<StylePicker presets={PRESETS} valor="" onChange={vi.fn()} />);
    const box = screen.getByTestId("preset-pp_box").querySelector(".sp-demo") as HTMLElement;
    expect(box.style.background).toBeTruthy();
    const classic = screen.getByTestId("preset-palavra_pop")
      .querySelector(".sp-demo") as HTMLElement;
    expect(classic.style.textShadow).toContain("px");
  });
});
