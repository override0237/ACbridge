# Frontend guide: "Vouch from Trade-group" checkbox

The backend is finished and tested. These are the pieces your frontend needs to add to the **vouch section**.
Nothing here lets the frontend decide anything: the UI only *asks*; the trade group's e-mail confirmation (not
the browser) is what qualifies an artisan.

## What the user sees

1. In the artisan's vouch section, next to the existing endorsement option, a new checkbox: **"Vouch from Trade-group"**.
2. Ticking it reveals: a **trade-group dropdown**, a **skill dropdown** (only skills not yet verified), an optional **note** (e.g. membership number) and a **Send request** button.
3. After sending: a status line, `Waiting for <group> to confirm by e-mail`. When the group confirms, the skill shows **Verified** with the group's name as a badge.
4. A trade group is **e-mailed a link**. It has **no account and does not use your frontend**: the backend serves the confirmation page at `/trade-group-vouches/confirm-page?token=…`.

## API calls (all JSON; send `Authorization: Bearer <token>` unless marked public)

| Purpose | Call |
|---|---|
| Fill the dropdown (public) | `GET /trade-groups` → `[{group_id, name, description}]` |
| Skills for the dropdown | `GET /artisans/{artisanId}` → `skills[]`; offer those with `verification_status !== "VERIFIED"` |
| Submit the checkbox form | `POST /artisans/{artisanId}/trade-group-vouches` body `{group_id, skill_id, note?}` → `201` with `status`, `message`, `email_status` |
| Show status | `GET /artisans/{artisanId}/trade-group-vouches` → list with `status`: `PENDING_CONFIRMATION`, `CONFIRMED`, `REJECTED`, `EXPIRED`, `REVOKED` |
| E-mail failed / link expired | `POST /artisans/{artisanId}/trade-group-vouches/{vouchId}/resend` |
| Public badge on a profile | `GET /artisans/{artisanId}` → `trade_group_vouches[] = {group_name, skill_name, confirmed_at}` |

Errors are `{"detail": "…"}`; show `detail` to the user. Useful ones: `409` already pending/verified or
"recently declined" (the artisan must wait 7 days), `404` group not active, `400` skill not on the profile.

**Individuals vs groups.** The existing person-to-person endorsement (`POST /artisans/{id}/endorsements`) now returns
`409 "You can only vouch for one artisan. Only trade groups can vouch for several artisans"` if the same person tries a
second artisan. Show that message; do not hide it.

## React component (copy, adapt styling)

```jsx
import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";   // CRA: process.env.REACT_APP_API_URL

async function api(path, token, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token && { Authorization: `Bearer ${token}` }) },
  });
  const body = res.status === 204 ? null : await res.json();
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Please check the form");
  return body;
}

export default function TradeGroupVouch({ artisanId, token }) {
  const [enabled, setEnabled] = useState(false);      // the "Vouch from Trade-group" checkbox
  const [groups, setGroups] = useState([]);
  const [skills, setSkills] = useState([]);
  const [vouches, setVouches] = useState([]);
  const [form, setForm] = useState({ group_id: "", skill_id: "", note: "" });
  const [message, setMessage] = useState("");

  const refresh = async () => {
    setVouches(await api(`/artisans/${artisanId}/trade-group-vouches`, token));
    const profile = await api(`/artisans/${artisanId}`);
    setSkills(profile.skills.filter((s) => s.verification_status !== "VERIFIED"));
  };

  useEffect(() => { api("/trade-groups").then(setGroups); refresh(); }, [artisanId]);

  const submit = async (e) => {
    e.preventDefault();
    try {
      const v = await api(`/artisans/${artisanId}/trade-group-vouches`, token, {
        method: "POST",
        body: JSON.stringify({ ...form, note: form.note || null }),
      });
      setMessage(v.message);
      refresh();
    } catch (err) { setMessage(err.message); }
  };

  const resend = (id) =>
    api(`/artisans/${artisanId}/trade-group-vouches/${id}/resend`, token, { method: "POST" })
      .then((v) => setMessage(v.message)).then(refresh).catch((e) => setMessage(e.message));

  return (
    <section>
      <label>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        {" "}Vouch from Trade-group
      </label>

      {enabled && (
        <form onSubmit={submit}>
          <select required value={form.group_id} onChange={(e) => setForm({ ...form, group_id: e.target.value })}>
            <option value="">Choose your trade group</option>
            {groups.map((g) => <option key={g.group_id} value={g.group_id}>{g.name}</option>)}
          </select>
          <select required value={form.skill_id} onChange={(e) => setForm({ ...form, skill_id: e.target.value })}>
            <option value="">Which skill?</option>
            {skills.map((s) => <option key={s.skill_id} value={s.skill_id}>{s.skill_name}</option>)}
          </select>
          <input placeholder="Membership no. (optional)" maxLength={500} value={form.note}
                 onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <button type="submit">Send request</button>
        </form>
      )}

      {message && <p role="status">{message}</p>}

      <ul>
        {vouches.map((v) => (
          <li key={v.vouch_id}>
            {v.group_name} / {v.skill_name}: <b>{v.status.replaceAll("_", " ")}</b> ({v.message})
            {["PENDING_CONFIRMATION", "EXPIRED"].includes(v.status) && (
              <button onClick={() => resend(v.vouch_id)}>Resend e-mail</button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
```

For plain HTML/JS the calls are identical: `fetch` the endpoints above and toggle the form's `hidden` attribute from the checkbox.

## Profile badge (customers)

On the artisan profile, render each `trade_group_vouches` entry as a badge, e.g. `✔ Vouched by Buea Electricians Association (Electrical Repair)`.
Keep it separate from the reputation score and from identity verification.

## Optional admin screen

| Purpose | Call (admin token) |
|---|---|
| Register a group (sends it a confirmation e-mail) | `POST /admin/trade-groups` `{name, email, description}` |
| List groups with counts | `GET /admin/trade-groups` |
| Resend the group's e-mail / suspend / activate | `POST /admin/trade-groups/{id}/resend-verification`, `/suspend`, `/activate` |
| Withdraw a vouch | `POST /admin/trade-group-vouches/{id}/revoke` `{notes}` |

## Notes

* In the demo, e-mail is **simulated** (`EMAIL_MODE=console`): nothing is really sent. Admins can read the "sent" messages at `GET /admin/dev/outbox` (that is how the demo script gets the confirmation link). For real e-mail set `EMAIL_MODE=smtp` and the `SMTP_*` variables.
* Set `PUBLIC_API_URL` in `backend/.env` to the address the trade group can reach (their link points there).
* To use your own confirmation page instead of the built-in one, call `GET /trade-group-vouches/details?token=` (read-only) and `POST /trade-group-vouches/respond` `{token, decision: "CONFIRM"|"REJECT"}`.
