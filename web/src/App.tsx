import { useRoute } from "./lib/router";
import Inbox from "./pages/Inbox";
import Placeholder from "./pages/Placeholder";
import Shell from "./shell/Shell";
import { ToastProvider } from "./ui/Toast";

function Screen() {
  const route = useRoute();
  switch (route.name) {
    case "inbox":
      return <Inbox />;
    case "review":
      return <Placeholder title="Review" />;
    case "vendors":
      return <Placeholder title="Vendors" />;
    case "exports":
      return <Placeholder title="Exports" />;
    case "insights":
      return <Placeholder title="Insights" />;
    case "settings":
      return <Placeholder title="Settings" />;
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
