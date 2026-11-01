import { useRoute } from "./lib/router";
import Inbox from "./pages/Inbox";
import Exports from "./pages/Exports";
import Insights from "./pages/Insights";
import Placeholder from "./pages/Placeholder";
import Vendors from "./pages/Vendors";
import Review from "./pages/Review";
import Settings from "./pages/Settings";
import Shell from "./shell/Shell";
import { ToastProvider } from "./ui/Toast";

function Screen() {
  const route = useRoute();
  switch (route.name) {
    case "inbox":
      return <Inbox />;
    case "review":
      return <Review key={route.id} id={route.id} />;
    case "vendors":
      return <Vendors />;
    case "exports":
      return <Exports />;
    case "insights":
      return <Insights />;
    case "settings":
      return <Settings />;
    default:
      return <Placeholder title="Not found" />;
  }
}

export default function App() {
  return (
    <ToastProvider>
      <Shell>
        <Screen />
      </Shell>
    </ToastProvider>
  );
}
