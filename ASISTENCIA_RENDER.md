# Guía de Configuración para Render + Supabase

Has creado el proyecto en Supabase: **`ukqoctvavgomdlydwran`**

Para que tu backend en Render funcione, necesitas configurar las siguientes **Environment Variables** (Variables de Entorno) en el Dashboard de Render:

## 1. SUPABASE_URL
*   **Valor:** `https://ukqoctvavgomdlydwran.supabase.co`

## 2. SUPABASE_KEY
Esta es tu llave pública para el cliente de Supabase.
1.  Ve a tu Dashboard de Supabase.
2.  Entra en **Project Settings** (engranaje abajo a la izquierda) -> **API**.
3.  Copia el valor de **`anon`** / `public`.

## 3. DATABASE_URL (¡Crucial!)
Esta es la cadena de conexión para que Python hable con PostgreSQL.
1.  Ve a **Project Settings** -> **Database**.
2.  Busca la sección **Connection String**.
3.  Selecciona la pestaña **URI**.
4.  **IMPORTANTE:** Cambia el Mode a **Transaction** (Puerto 6543). Python funciona mejor así.
5.  Copia la cadena que aparece. Se verá algo así:
    `postgresql://postgres.ukqoctvavgomdlydwran:[TU_PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require`
6.  **Reemplaza `[TU_PASSWORD]`** (o `[YOUR-PASSWORD]`) con la contraseña que creaste para la base de datos al iniciar el proyecto.

---

## Confirmación en Render
Cuando Render te pida las variables, pega estos 3 valores.
*   Si falla la conexión a base de datos, verifica que la contraseña sea correcta.
*   Si dice "Missing dependencies", verifica que `requirements.txt` esté instalado (Render lo hace solo).

¡Tu sistema de facturación estará listo en la nube! 🚀
