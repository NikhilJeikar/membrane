"""Interactive review of pending memory proposals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from shadow_pa.memory.models import MemoryCategory, MemoryProposal, ProposalStatus
from shadow_pa.memory.store import MemoryStore

if TYPE_CHECKING:
    from rich.console import Console


def _proposal_body(proposal: MemoryProposal) -> str:
    lines: list[str] = [
        f"[bold]Category:[/bold] {proposal.category.value}",
        f"[bold]Source:[/bold] {proposal.source.value}",
    ]
    if proposal.reason:
        lines.append(f"[bold]Reason:[/bold] {proposal.reason}")

    if proposal.profile:
        lines.append(f"[bold]Key:[/bold] {proposal.profile.key}")
        lines.append(f"[bold]Value:[/bold] {proposal.profile.value}")
        lines.append(f"[bold]Confidence:[/bold] {proposal.profile.confidence:.2f}")
        if proposal.profile.evidence:
            lines.append("[bold]Evidence:[/bold]")
            for item in proposal.profile.evidence:
                lines.append(f"  • {item}")

    if proposal.preference:
        lines.append(f"[bold]Key:[/bold] {proposal.preference.key}")
        lines.append(f"[bold]Value:[/bold] {proposal.preference.value}")
        lines.append(f"[bold]Strength:[/bold] {proposal.preference.strength:.2f}")
        if proposal.preference.evidence:
            lines.append("[bold]Evidence:[/bold]")
            for item in proposal.preference.evidence:
                lines.append(f"  • {item}")

    if proposal.episode:
        lines.append(f"[bold]Summary:[/bold]\n{proposal.episode.summary}")
        if proposal.episode.tags:
            lines.append(f"[bold]Tags:[/bold] {', '.join(proposal.episode.tags)}")
        if proposal.episode.raw_ref:
            lines.append(f"[bold]From:[/bold] {proposal.episode.raw_ref}")

    return "\n".join(lines)


def _existing_memory_note(store: MemoryStore, proposal: MemoryProposal) -> str | None:
    if proposal.profile:
        for entry in store.load_profile():
            if entry.key == proposal.profile.key:
                if entry.value == proposal.profile.value:
                    return f"Already in memory with same value ({entry.key})"
                return (
                    f"Key [cyan]{entry.key}[/cyan] exists — "
                    f"current: {entry.value!r} → proposed: {proposal.profile.value!r}"
                )
    if proposal.preference:
        for entry in store.load_preferences():
            if entry.key == proposal.preference.key:
                if entry.value == proposal.preference.value:
                    return f"Already in memory with same value ({entry.key})"
                return (
                    f"Key [cyan]{entry.key}[/cyan] exists — "
                    f"current: {entry.value!r} → proposed: {proposal.preference.value!r}"
                )
    return None


def proposal_to_dict(proposal: MemoryProposal, store: MemoryStore | None = None) -> dict:
    """Serialize a proposal for API / UI."""
    summary = ""
    detail: dict = {}
    if proposal.profile:
        summary = f"{proposal.profile.key} = {proposal.profile.value}"
        detail = proposal.profile.model_dump(mode="json")
    elif proposal.preference:
        summary = f"{proposal.preference.key} = {proposal.preference.value}"
        detail = proposal.preference.model_dump(mode="json")
    elif proposal.episode:
        summary = proposal.episode.summary[:120]
        detail = proposal.episode.model_dump(mode="json")

    note = _existing_memory_note(store, proposal) if store else None
    return {
        "id": proposal.id,
        "category": proposal.category.value,
        "status": proposal.status.value,
        "source": proposal.source.value,
        "reason": proposal.reason,
        "created_at": proposal.created_at.isoformat(),
        "summary": summary,
        "detail": detail,
        "existing_note": note,
        "proposal": proposal.model_dump(mode="json"),
    }


def run_interactive_review(
    store: MemoryStore,
    console: Console,
    *,
    category: MemoryCategory | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Review pending proposals one at a time. Returns action counts."""
    proposals = store.list_proposed(ProposalStatus.PENDING)
    if category:
        proposals = [p for p in proposals if p.category == category]
    if limit is not None and limit > 0:
        proposals = proposals[:limit]

    counts = {"approved": 0, "rejected": 0, "skipped": 0, "quit": 0}
    total = len(proposals)
    if total == 0:
        console.print("[yellow]No pending proposals to review.[/yellow]")
        return counts

    console.print(
        f"[cyan]Reviewing[/cyan] {total} proposal(s). "
        "[bold]a[/bold]=approve  [bold]r[/bold]=reject  [bold]s[/bold]=skip  [bold]q[/bold]=quit\n"
    )

    for index, proposal in enumerate(proposals, start=1):
        note = _existing_memory_note(store, proposal)
        subtitle = f"{index}/{total} · {proposal.id}"
        body = _proposal_body(proposal)
        if note:
            body += f"\n\n[yellow]Note:[/yellow] {note}"

        console.print(
            Panel(
                body,
                title=f"Memory proposal · {proposal.category.value}",
                subtitle=subtitle,
                border_style="blue",
            )
        )

        while True:
            choice = Prompt.ask(
                "Action",
                choices=["a", "r", "s", "q", "A", "R", "S", "Q"],
                default="s",
                show_choices=False,
            ).lower()
            if choice == "a":
                store.approve(proposal.id)
                console.print(f"[green]Approved[/green] {proposal.id}\n")
                counts["approved"] += 1
                break
            if choice == "r":
                store.reject(proposal.id)
                console.print(f"[red]Rejected[/red] {proposal.id}\n")
                counts["rejected"] += 1
                break
            if choice == "s":
                console.print(f"[dim]Skipped[/dim] {proposal.id}\n")
                counts["skipped"] += 1
                break
            if choice == "q":
                counts["quit"] = total - index + 1
                console.print("[yellow]Review stopped.[/yellow]")
                return counts

    summary = Text()
    summary.append("Done — ", style="bold")
    summary.append(f"approved {counts['approved']}", style="green")
    summary.append(", ")
    summary.append(f"rejected {counts['rejected']}", style="red")
    summary.append(", ")
    summary.append(f"skipped {counts['skipped']}", style="dim")
    console.print(summary)
    return counts
