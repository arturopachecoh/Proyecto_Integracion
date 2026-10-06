/**
 * Click-through local contra http://127.0.0.1:3000
 * Uso: npx playwright test tests/clickthrough.spec.ts
 */
import { test, expect } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL || "http://127.0.0.1:3000";

test.describe("portal y visor", () => {
  test("catálogo → carro → checkout mock → resultado de pago", async ({ page }) => {
    await page.goto(BASE + "/");
    await expect(page.getByRole("heading", { name: /Kits clínicos/i })).toBeVisible();

    const kit = page.locator("article.card", { hasText: "KIT-RESP-ADULTO" });
    await expect(kit).toBeVisible();
    await kit.getByRole("button", { name: /Agregar/i }).click();
    await expect(page.getByRole("status")).toContainText(/carro/i);

    await page.getByRole("link", { name: /Carro/i }).click();
    await expect(page.getByRole("heading", { name: /Carro de compras/i })).toBeVisible();
    await expect(page.getByText("KIT-RESP-ADULTO")).toBeVisible();
    await page.getByRole("link", { name: /Confirmar compra/i }).click();

    await expect(page.getByRole("heading", { name: /Confirmar compra/i })).toBeVisible();
    await page.getByLabel("Nombre").fill("Ana Clickthrough");
    await page.getByLabel("Correo").fill("ana.click@test.cl");
    await page.getByRole("button", { name: /Pagar/i }).click();

    await page.waitForURL(/\/pago\//, { timeout: 20000 });
    await expect(page.getByRole("heading")).toBeVisible();
    await expect(page.locator("h1")).toHaveText(/Pago (exitoso|cancelado)|Error de pago/);
  });

  test("visor: buscar lote y click-through aguas arriba/abajo", async ({ page }) => {
    await page.goto(BASE + "/trazabilidad");
    await expect(page.getByRole("heading", { name: /Trazabilidad de lote/i })).toBeVisible();

    const buscador = page.getByLabel("Código de lote");
    await buscador.fill("L-DEMO-BLIAMOXI-7F3A");
    await page.getByRole("button", { name: "Buscar" }).click();

    await expect(page.getByText("BLI-AMOXI-500").first()).toBeVisible();
    await expect(page.getByText("Unidades producidas")).toBeVisible();
    await expect(page.getByText("API-AMOXI-500")).toBeVisible();
    await expect(page.getByText("KIT-RESP-ADULTO")).toBeVisible();

    await page.getByRole("link", { name: /Ver lote L-DEMO-APIAMOX-11C2/i }).click();
    await expect(page).toHaveURL(/lote=L-DEMO-APIAMOX-11C2/);
    await expect(page.getByText("API-AMOXI-500").first()).toBeVisible();

    await page.getByRole("link", { name: /Ver lote L-DEMO-BLIAMOXI-7F3A/i }).click();
    await expect(page).toHaveURL(/lote=L-DEMO-BLIAMOXI-7F3A/);

    await page.getByRole("link", { name: /Ver lote L-DEMO-KITRESP-AXE1/i }).click();
    await expect(page).toHaveURL(/lote=L-DEMO-KITRESP-AXE1/);
    await expect(page.getByText("KIT-RESP-ADULTO").first()).toBeVisible();
  });
});
