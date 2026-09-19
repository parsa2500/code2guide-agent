import React from "react";

export default function TenderForm() {
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const data = new FormData(form);
    await fetch("/api/Tenders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: data.get("title"),
        description: data.get("description"),
      }),
    });
  };

  return (
    <form onSubmit={onSubmit}>
      <h2>ثبت مناقصه جدید</h2>
      <input name="title" label="عنوان مناقصه" required />
      <input name="description" label="شرح مناقصه" />
      <button type="submit">ثبت نهایی و ارسال مناقصه</button>
    </form>
  );
}
