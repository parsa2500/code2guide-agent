import TenderForm from "./pages/Tenders/Create";
import Tenders from "./pages/Tenders/List";
import Dashboard from "./pages/Dashboard";

export const menuConfig = [
  {
    title: "مدیریت مناقصات",
    path: "/tenders",
    children: [{ title: "ثبت مناقصه جدید", path: "/tenders/create" }],
  },
  { title: "داشبورد کاربری", path: "/dashboard" },
];

export const AppRouter = () => (
  <Routes>
    <Route path="/tenders" element={<Tenders />} />
    <Route path="/tenders/create" element={<TenderForm />} />
    <Route path="/dashboard" element={<Dashboard />} />
  </Routes>
);
