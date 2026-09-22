import { useState, type FormEvent } from "react";
import { ArrowRight, LocateFixed, LockKeyhole } from "lucide-react";
import { useAuth } from "../auth";
import { ErrorNotice } from "../components/ui";

export function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <a className="brand" href="/">
          <span className="brand-mark">
            <LocateFixed aria-hidden="true" />
          </span>
          <span>GeoPol</span>
        </a>
        <div className="login-story-copy">
          <h1>Normalización y geocodificación</h1>
          <p>
            Importa los registros de la PNP, consulta sus resultados y atiende
            los casos pendientes.
          </p>
        </div>
        <div className="login-grid" aria-hidden="true">
          <span className="grid-pin one" />
          <span className="grid-pin two" />
          <span className="grid-pin three" />
        </div>
      </section>
      <section className="login-form-panel">
        <form onSubmit={submit} className="login-form">
          <div className="login-lock">
            <LockKeyhole size={24} aria-hidden="true" />
          </div>
          <h2>Bienvenido a GeoPol</h2>
          <p>Ingresa con la cuenta asignada por tu administrador.</p>
          <ErrorNotice error={error} />
          <label htmlFor="username">Usuario</label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            required
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="button primary full" disabled={busy}>
            {busy ? "Validando acceso…" : "Ingresar al espacio de trabajo"}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
          <p className="fine-print">
            El acceso y las decisiones se registran en la bitácora de auditoría.
          </p>
        </form>
      </section>
    </main>
  );
}
