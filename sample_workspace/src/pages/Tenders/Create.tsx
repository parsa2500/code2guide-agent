import React from "react";

export default function TenderForm() {
  return (
    <form>
      <h2>ثبت مناقصه جدید</h2>
      <input name="title" label="عنوان مناقصه" required />
      <input name="description" label="شرح مناقصه" />
      <button type="submit">ثبت نهایی و ارسال مناقصه</button>
    </form>
  );
}
