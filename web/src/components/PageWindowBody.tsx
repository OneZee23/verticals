/* A web page in a window: framed only when the server found that it can be;
   otherwise the window says so and offers Chrome. */
import { onMounted, ref, watch } from '../reactivity'
import { AppIcon } from './AppIcon'
import { framable } from '../lib/pages'
import { fallthrough } from '../bind'
import { tracked } from '../tracked'
import { useSetup } from '../setup'
import './pageWindowBody.css'

interface Props {
  url: string
}

export const PageWindowBody = tracked(function PageWindowBody({ url, ...attrs }: Props & Record<string, unknown>) {
  const s = useSetup({ url }, (props) => {
    const state = ref<'checking' | 'framed' | 'refused'>('checking')

    async function check(): Promise<void> {
      state.value = 'checking'
      state.value = (await framable(props.url)) ? 'framed' : 'refused'
    }
    onMounted(check)
    watch(() => props.url, check)
    return { state }
  })
  const state = s.state.value
  return (
    <div {...fallthrough({ className: 'page-window', 'data-state': state, 'data-role': 'page-window' }, attrs)}>
      {state === 'framed' ? (
        <iframe className="page-window__frame" src={url} title="Web page" referrerPolicy="no-referrer"></iframe>
      ) : state === 'refused' ? (
        <div className="page-window__refused" data-role="page-refused">
          <p>This page can't open here</p>
          <a href={url} target="_blank" rel="noreferrer" data-role="open-in-chrome">Open in Chrome <AppIcon name="arrow-up-right" size={16} /></a>
        </div>
      ) : (
        <p className="page-window__checking">Opening…</p>
      )}
    </div>
  )
})
