import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Star, Trash2 } from "lucide-react";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { EmptyState } from "../components/ui/EmptyState";
import { Input } from "../components/ui/Input";
import { Spinner } from "../components/ui/Spinner";
import { Table, TBody, TD, TH, THead, TR } from "../components/ui/Table";
import { useToast } from "../components/ui/Toast";
import { api, BookEntry } from "../api";
import { cn } from "../lib/utils";

type FormState = {
  title: string;
  author: string;
  rating: number | null;
  notes: string;
  readYear: string;
};

const emptyForm = (): FormState => ({
  title: "",
  author: "",
  rating: null,
  notes: "",
  readYear: "",
});

function RatingStars({
  value,
  onChange,
}: {
  value: number | null;
  onChange?: (rating: number | null) => void;
}) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => {
        const filled = value != null && n <= value;
        const star = (
          <Star
            className={cn(
              "h-4 w-4",
              filled ? "fill-amber-400 text-amber-400" : "text-ink-muted"
            )}
          />
        );
        if (!onChange) return <span key={n}>{star}</span>;
        return (
          <button
            key={n}
            type="button"
            aria-label={`${n} star${n > 1 ? "s" : ""}`}
            onClick={() => onChange(value === n ? null : n)}
            className="rounded p-0.5 transition hover:bg-surface-hover"
          >
            {star}
          </button>
        );
      })}
    </div>
  );
}

export default function BooksPage() {
  const [items, setItems] = useState<BookEntry[] | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<BookEntry | null>(null);
  const [editing, setEditing] = useState<BookEntry | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      const data = await api.listBooks();
      setItems(data.items);
    } catch (err) {
      console.error(err);
      toast("error", "Failed to load books");
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  function openAdd() {
    setEditing(null);
    setForm(emptyForm());
    setModalOpen(true);
  }

  function openEdit(book: BookEntry) {
    setEditing(book);
    setForm({
      title: book.title,
      author: book.author,
      rating: book.rating,
      notes: book.notes,
      readYear: book.read_year != null ? String(book.read_year) : "",
    });
    setModalOpen(true);
  }

  async function saveBook() {
    if (!form.title.trim()) {
      toast("error", "Title is required");
      return;
    }
    const readYear = form.readYear.trim() === "" ? null : Number(form.readYear);
    if (readYear !== null && (!Number.isInteger(readYear) || readYear < 1900 || readYear > 2200)) {
      toast("error", "Year read must be between 1900 and 2200");
      return;
    }
    setBusy(true);
    try {
      const body = {
        title: form.title.trim(),
        author: form.author.trim(),
        rating: form.rating,
        notes: form.notes.trim(),
        read_year: readYear,
      };
      if (editing) {
        await api.updateBook(editing.id, body);
      } else {
        await api.addBook(body);
      }
      setModalOpen(false);
      toast(
        "success",
        editing ? "Book updated" : "Book added",
        "Saved to episode memory so the assistant knows you read it."
      );
      await load();
    } catch (err) {
      toast("error", "Failed to save book", String(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await api.deleteBook(deleteTarget.id);
      setDeleteTarget(null);
      toast("success", "Book removed", "Linked episode memory was removed too.");
      await load();
    } catch (err) {
      toast("error", "Failed to delete book", String(err));
    } finally {
      setBusy(false);
    }
  }

  if (items === null) return <Spinner label="Loading books…" />;

  return (
    <>
      <PageHeader
        title="Books"
        description="Books you've read. Each entry is stored as episode memory and exported as training data, so the model knows what you've read."
      />

      <div className="mb-4">
        <Button icon={<Plus className="h-4 w-4" />} onClick={openAdd}>
          Add book
        </Button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="No books yet"
          description="Add books you've read. They become episode memory and SFT training rows on the next export."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Title</TH>
              <TH>Author</TH>
              <TH>Rating</TH>
              <TH>Year read</TH>
              <TH>Notes</TH>
              <TH className="w-24" />
            </TR>
          </THead>
          <TBody>
            {items.map((book) => (
              <TR key={book.id}>
                <TD className="font-medium">{book.title}</TD>
                <TD className="text-ink-secondary">{book.author || "—"}</TD>
                <TD>
                  {book.rating != null ? <RatingStars value={book.rating} /> : (
                    <span className="text-ink-muted">—</span>
                  )}
                </TD>
                <TD className="text-ink-secondary">{book.read_year ?? "—"}</TD>
                <TD className="max-w-sm text-ink-secondary">
                  <span className="line-clamp-2">{book.notes || "—"}</span>
                </TD>
                <TD>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Edit"
                      icon={<Pencil className="h-3.5 w-3.5" />}
                      onClick={() => openEdit(book)}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Delete"
                      icon={<Trash2 className="h-3.5 w-3.5" />}
                      onClick={() => setDeleteTarget(book)}
                    />
                  </div>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Dialog
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editing ? "Edit book" : "Add book"}
        description="Stored as episode memory and used to build training recall examples."
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={saveBook}>
              {editing ? "Save" : "Add"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Title"
            placeholder="e.g. Thinking, Fast and Slow"
            value={form.title}
            onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
          />
          <div className="grid grid-cols-[1fr_7rem] gap-3">
            <Input
              label="Author"
              placeholder="e.g. Daniel Kahneman"
              value={form.author}
              onChange={(e) => setForm((prev) => ({ ...prev, author: e.target.value }))}
            />
            <Input
              label="Year read"
              type="number"
              min={1900}
              max={2200}
              placeholder="2026"
              value={form.readYear}
              onChange={(e) => setForm((prev) => ({ ...prev, readYear: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] font-medium text-ink-secondary">Rating</span>
            <RatingStars
              value={form.rating}
              onChange={(rating) => setForm((prev) => ({ ...prev, rating }))}
            />
          </div>
          <Input
            label="Notes / takeaway"
            placeholder="What you got out of it (used in training examples)"
            value={form.notes}
            onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
          />
        </div>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Remove book"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={busy} onClick={confirmDelete}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-secondary">
          Remove <strong className="text-ink-primary">{deleteTarget?.title}</strong>? Its linked
          episode memory will also be deleted.
        </p>
      </Dialog>
    </>
  );
}
